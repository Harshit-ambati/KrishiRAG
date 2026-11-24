import math
import os
from datetime import date, datetime, timedelta

import httpx
from pydantic import BaseModel

from locations import LOCATIONS

FREE_URL = "https://api.open-meteo.com/v1/forecast"
PAID_URL = "https://customer-api.open-meteo.com/v1/forecast"
DAILY_UNITS = {
    "rain_sum": "mm", "showers_sum": "mm",
    "temperature_2m_min": "°C", "temperature_2m_max": "°C",
    "wind_speed_10m_max": "km/h",
}
FORECAST_DAYS = 7
SURFACE_MOISTURE = "soil_moisture_0_to_1cm"


class Forecast(BaseModel):
    day: date
    latitude: float
    longitude: float
    retrieved_at: datetime
    rainfall_mm: float
    low_c: float
    high_c: float
    wind_kmh: float
    soil_moisture_m3_m3: float | None = None


def forecast_parameters(latitude, longitude, day, last_day=None):
    return {
        "latitude": latitude, "longitude": longitude, "timezone": "Asia/Kolkata",
        "daily": ",".join(DAILY_UNITS), "start_date": day.isoformat(), "end_date": (last_day or day).isoformat(),
        "hourly": SURFACE_MOISTURE,
    }


def forecast_configured(state, district, day, today):
    return (day is not None and os.environ.get("AGRIRAG_LIVE_WEATHER") == "1"
            and bool(LOCATIONS.get((state, district))) and 0 <= (day - today).days < FORECAST_DAYS)


def daily_surface_moisture(payload, days):
    units, hourly = payload.get("hourly_units"), payload.get("hourly")
    if not isinstance(units, dict) or units.get(SURFACE_MOISTURE) != "m³/m³" or not isinstance(hourly, dict):
        return {}
    times, values = hourly.get("time"), hourly.get(SURFACE_MOISTURE)
    expected = [f"{day.isoformat()}T{hour:02d}:00" for day in days for hour in range(24)]
    if times != expected or not isinstance(values, list) or len(values) != len(expected):
        return {}
    estimates = {}
    for index, day in enumerate(days):
        samples = values[index * 24:(index + 1) * 24]
        if all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1 for value in samples):
            estimates[day] = round(sum(samples) / 24, 4)
    return estimates


def fetch_forecast_days(state, district, first_day, last_day, now):
    first_day = max(first_day, now.date())
    last_day = min(last_day, now.date() + timedelta(days=FORECAST_DAYS - 1))
    if first_day > last_day or not forecast_configured(state, district, first_day, now.date()):
        return {}
    latitude, longitude = LOCATIONS[state, district]
    params = forecast_parameters(latitude, longitude, first_day, last_day)
    days = [first_day + timedelta(days=offset) for offset in range((last_day - first_day).days + 1)]
    key = os.environ.get("OPEN_METEO_API_KEY", "").strip()
    if key:
        params["apikey"] = key
    try:
        response = httpx.get(PAID_URL if key else FREE_URL, params=params, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
        if payload["timezone"] != "Asia/Kolkata" or payload["daily"]["time"] != [day.isoformat() for day in days]:
            return {}
        daily, units = payload["daily"], payload["daily_units"]
        if any(units[field] != unit or not isinstance(daily[field], list) or len(daily[field]) != len(days)
               for field, unit in DAILY_UNITS.items()):
            return {}
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return {}
    estimates = daily_surface_moisture(payload, days)
    forecasts = {}
    for index, day in enumerate(days):
        values = [daily[field][index] for field in DAILY_UNITS]
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
            continue
        rain, showers, low, high, wind = values
        if min(rain, showers, wind) < 0 or low > high:
            continue
        forecasts[day] = Forecast(day=day, latitude=latitude, longitude=longitude, retrieved_at=now,
                                  rainfall_mm=round(rain + showers, 2), low_c=low, high_c=high, wind_kmh=wind,
                                  soil_moisture_m3_m3=estimates.get(day))
    return forecasts


def fetch_forecast(state, district, day, now):
    if day is None:
        return None
    return fetch_forecast_days(state, district, day, day, now).get(day)


def forecast_passage(forecast, state, district):
    day = forecast.day.isoformat()
    stamp = forecast.retrieved_at.isoformat(timespec="seconds")
    excerpt = (f"Requested point: {forecast.latitude}, {forecast.longitude}. "
               f"Retrieved {stamp}. Forecast for {day}: {forecast.rainfall_mm:g} mm rainfall (rain and showers), "
               f"{forecast.low_c:g}–{forecast.high_c:g} °C, maximum wind {forecast.wind_kmh:g} km/h.")
    if forecast.soil_moisture_m3_m3 is not None:
        excerpt += f" Daily mean modelled surface soil moisture (0–1 cm): {forecast.soil_moisture_m3_m3 * 100:.1f}% by volume."
    return {
        "id": f"open-meteo:{state}:{district}:{stamp}", "source_id": "open-meteo-forecast",
        "title": "Weather Forecast API", "publisher": "Open-Meteo",
        "original_url": "https://open-meteo.com/en/docs", "version": stamp,
        "issue_date": None, "sha256": None, "state_id": state, "district_id": district,
        "crop": None, "crop_stage": None, "topic": "district-rainfall-forecast", "page_number": None,
        "section": f"Daily forecast at {forecast.latitude}, {forecast.longitude}",
        "content": excerpt, "evidence_language": "en", "effective_from": day, "effective_until": day,
    }
