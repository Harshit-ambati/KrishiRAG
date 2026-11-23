# Andhra Pradesh pilot evidence audit

Reviewed on 23 November 2026. **Krishna and West Godavari both qualify** for the dated pilot. The verified overlap between paddy guidance and the district rainfall forecasts is **24–25 November 2026**. Outside that overlap, these versions alone do not establish district coverage for weather-sensitive paddy decisions.

| Official source and edition | Actual scope and reviewed locator | Usable evidence and limits |
| --- | --- | --- |
| IMD / AMFU Guntur, Andhra Pradesh Agromet Bulletin **93/2026**, issued 20 November 2026, valid 21–25 November | PDF p. 21, **Krishna & NTR districts**, Rice row. PDF p. 24, **West Godavari & Eluru districts**, Rice row. Only Krishna and West Godavari were indexed. | Soil moisture and avoidance of excess irrigation during grain filling and hardening. Harvest at physiological maturity and grain drying before storage. The harvest bullet sets a maturity condition and gives no weather-safe harvest time. No irrigation depth or interval is specified. [Official IMD bulletin](https://mausam.imd.gov.in/visakhapatnam/mcdata/APAgromet.pdf) |
| IMD Amaravati, 5 Days Value Added Forecast **94/2026**, issued 23 November 2026, valid 24–28 November | PDF p. 1, English and Telugu district tables. Five explicit date rows each for **Krishna** and **West Godavari**. | District rainfall forecasts for field planning, with date and units checked against the table. These values describe a forecast for the district. The blank warning column does not establish an absence of hazards. [Official IMD forecast](https://mausam.imd.gov.in/amaravati/mcdata/APvaf.pdf) |
| ANGRAU, *Vyavasayam*, **March 2023** | PDF and printed p. 8, upper-left paddy harvest section, second bullet. The Maruteru author’s affiliation does not specify geographic applicability. | General Telugu post-harvest grain drying background. No day-level issue date or validity window is stated for this passage. It does not establish coverage for either district. [Official ANGRAU issue](https://angrau.ac.in/downloads/Publications/Vyavasayam%20March_Book_01-023-23_compressed.pdf) |

I verified the original publisher URLs by downloading the PDFs. The IMD endpoints returned newer editions than their indexed copies. I checked the rendered AMFU district headings, crop and stage columns, and moisture and harvest bullets. I compared the parallel rainfall tables and checked the ANGRAU passage from the page image because its legacy font produced unreliable extracted Telugu. The seed stores reviewed paraphrases or forecast values, PDF page numbers, section locators, issue and validity dates, versions, and the SHA-256 of each reviewed PDF.

The audited IMD URLs are rotating endpoints. Preserve the matching original PDF when verifying a new edition. The local evidence database holds the three verified snapshots. The checked-in seed can recreate the reviewed records without redistributing the full PDFs. A redeployment can attach an original only if its SHA-256 matches the seed.

This audit establishes no additional district coverage, spray-timing guidance, irrigation volumes, or rolling weather feed. The university background passage is excluded from district decisions because its geographic applicability is unspecified. The farmer question endpoint uses the approved catalog by default. The explicitly selected demo scenarios remain labeled.

## Evidence maintenance check, 23 November 2026

The reviewed IMD paddy and district forecast editions already have exact originals in the local evidence catalog. The maintenance report flags the reviewed district rainfall rows for Krishna and West Godavari as valid through **28 November 2026**. Their copies remain available from the protected source records.

The original Uttarakhand organic chilli PDF was attached to the approved record after its checksum matched the audited edition.

IMD's Andhra Pradesh Agromet Bulletin **94/2026**, issued **23 November 2026** and covering **24–28 November 2026**, was saved in the local review inbox as `data/evidence-inbox/ap-agromet-2026-11-23.pdf`. Its SHA-256 is `7a930941f6df33265f048acad099763611e85f7814ce44a87d036015206ad7de`. Treat it as a candidate. Review the specific Krishna and West Godavari crop rows, stages, and recommended actions before publishing any passages. The separate district forecast needs its own edition and date check. [IMD agromet bulletin](https://mausam.imd.gov.in/visakhapatnam/mcdata/APAgromet.pdf)

## Nationwide coverage baseline

The seeded catalog evaluated for **24 November 2026** includes **36 states and union territories and 783 districts**. It has applicable crop guidance in **54 districts across four states**, including **three districts with district-specific guidance**. Three districts have an approved rainfall forecast for that date. All 783 districts have a reference point for optional live weather. A reference point is distinct from a reviewed district forecast.

| Official source and edition | Reviewed scope and locator | Applicability |
| --- | --- | --- |
| IMD and ICAR Central Institute for Cotton Research, *Agromet Advisory Bulletin for Nagpur District*, issued 23 November 2026 | Nagpur district, Maharashtra. PDF page 1, rainfall row and mature-paddy note in General Advisory. | The table lists **0 mm** for 24–28 November. The accompanying dry-weather narrative ends on 27 November, so harvest and threshing guidance for mature paddy applies only during **24–27 November**. The audited SHA-256 is `1505a8b7150da66b6f409728e47fea7ddd9d9e1b08bd279e963e707a6b77d19d`. [IMD Nagpur bulletin](https://mausam.imd.gov.in/imd_latest/contents/agromet/agromet-data/district/current/english-pdf/Nagpur.pdf) |

The [IMD district bulletin index](https://mausam.imd.gov.in/responsive/agromet_adv_ser_district_current_en.php) and [ICAR-CRIDA district contingency plan directory](https://www.icar-crida.res.in/Crop_Contingency_Plan.html) are starting points for finding sources. Match the publisher’s district heading and boundaries to the current district ID. Contingency plans support only their stated rainfall, season, crop, and field conditions. The documented IMD district rainfall distribution API returned HTTP 401 when checked without credentials. Its documented station coverage percentages are distinct from rainfall amounts in millimetres. [IMD API reference](https://api.imd.gov.in/public/api_reference.html)
