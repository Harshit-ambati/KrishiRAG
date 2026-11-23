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


class Forecast(BaseModel):
    day: date
    latitude: float
    longitude: float
    retrieved_at: datetime
    rainfall_mm: float
    low_c: float
    high_c: float
    wind_kmh: float


def forecast_parameters(latitude, longitude, day):
    return {
        "latitude": latitude, "longitude": longitude, "timezone": "Asia/Kolkata",
        "daily": ",".join(DAILY_UNITS), "start_date": day.isoformat(), "end_date": day.isoformat(),
    }


def fetch_forecast(state, district, day, now):
    location = LOCATIONS.get((state, district))
    if not location or day is None or not 0 <= (day - now.date()).days < FORECAST_DAYS:
        return None
    if os.environ.get("AGRIRAG_LIVE_WEATHER") != "1":
        return None
    latitude, longitude = location
    params = forecast_parameters(latitude, longitude, day)
    key = os.environ.get("OPEN_METEO_API_KEY", "").strip()
    if key:
        params["apikey"] = key
    try:
        response = httpx.get(PAID_URL if key else FREE_URL, params=params, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
        if payload["timezone"] != "Asia/Kolkata" or payload["daily"]["time"] != [day.isoformat()]:
            return None
        daily, units = payload["daily"], payload["daily_units"]
        values = []
        for field, unit in DAILY_UNITS.items():
            value, = daily[field]
            if units[field] != unit or type(value) not in (int, float) or not math.isfinite(value):
                return None
            values.append(value)
        rain, showers, low, high, wind = values
        if min(rain, showers, wind) < 0 or low > high:
            return None
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None
    return Forecast(day=day, latitude=latitude, longitude=longitude, retrieved_at=now,
                    rainfall_mm=round(rain + showers, 2), low_c=low, high_c=high, wind_kmh=wind)


def forecast_passage(forecast, state, district):
    day = forecast.day.isoformat()
    stamp = forecast.retrieved_at.isoformat(timespec="seconds")
    excerpt = (f"Requested point: {forecast.latitude}, {forecast.longitude}. "
               f"Retrieved {stamp}. Forecast for {day}: {forecast.rainfall_mm:g} mm rainfall (rain and showers), "
               f"{forecast.low_c:g}–{forecast.high_c:g} °C, maximum wind {forecast.wind_kmh:g} km/h.")
    return {
        "id": f"open-meteo:{state}:{district}:{stamp}", "source_id": "open-meteo-forecast",
        "title": "Weather Forecast API", "publisher": "Open-Meteo",
        "original_url": "https://open-meteo.com/en/docs", "version": stamp,
        "issue_date": None, "sha256": None, "state_id": state, "district_id": district,
        "crop": None, "crop_stage": None, "topic": "district-rainfall-forecast", "page_number": None,
        "section": f"Daily forecast at {forecast.latitude}, {forecast.longitude}",
        "content": excerpt, "evidence_language": "en", "effective_from": day, "effective_until": day,
    }
