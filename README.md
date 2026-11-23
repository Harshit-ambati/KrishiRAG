# AgriRAG

AgriRAG is an evidence-grounded paddy advisory app. The Andhra Pradesh pilot covers Krishna and West Godavari. Both districts have paddy guidance from AMFU Guntur in [IMD Agromet Bulletin 87/2026](https://mausam.imd.gov.in/visakhapatnam/mcdata/APAgromet.pdf) and named rows in the [IMD Amaravati district forecast](https://mausam.imd.gov.in/amaravati/mcdata/District_Forecast.pdf).

## Run locally

From this folder, install the server dependencies and start FastAPI.

```sh
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

Open the [farmer interface](http://127.0.0.1:8765). It uses plain HTML, CSS, and JavaScript without a build step or API key. The form and its results are available in English, Telugu, and Hindi. The demo scenario selector demonstrates five statuses. In automatic mode, a deterministic fixture matches the question and checks for missing field details. The resulting advice and sources are examples.

Open the [evidence archive](http://127.0.0.1:8765/archive/) for the dated lookup. Choose **View archived advisory** to load an example for Krishna on 3 November 2026. The demo and the archive share the state and district configuration. Set `placeholder: true` on a district to label it as a demo district in the farmer interface.

## Advisory API

Open the [API documentation](http://127.0.0.1:8765/docs) to try `POST /api/advisories`. For a new session, send a body like this.

```json
{
  "state_id": "andhra-pradesh",
  "district_id": "krishna",
  "crop": "paddy",
  "crop_stage": "unknown",
  "question": "Do I need to irrigate after rain?",
  "language": "en"
}
```

When the response asks for the crop stage, send `session_id` from the response and `crop_stage`, such as `tillering`. When it asks about field conditions, send `session_id` and `field_observations`. The session keeps the original question, state, district, and crop. A follow-up can set `language` to `en`, `te`, or `hi`. To ask a new question, omit `session_id`.

For a specific demo, add `demo_scenario` when starting the session. The available values are `supported`, `conditional`, `clarification`, `coverageGap`, and `conflict`. An unknown crop stage prompts for clarification first. The optional `Idempotency-Key` request header replays the same response when a client retries the same body and key.

The server stores the original question and farm context in `data/advisories.sqlite3` by default. Set `AGRIRAG_DB_PATH` to use a different SQLite file.

## Verify

Run `node --test` to verify the archive retrieval, or install the API test dependencies and run the Python suite.

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s test -p "test_*.py"
```

## Evidence review

The [pilot audit](EVIDENCE_AUDIT.md) records the reviewed districts, source editions, supported uses, and coverage window. Load the approved passages into the local SQLite database with `python evidence_seed.py`. If you have the three original PDFs listed in `pilot_evidence.json`, supply their directory with `--snapshots`. The importer checks every file against the audited SHA-256 before attaching it. Re-running the seed preserves existing records, including archived versions.

Set `AGRIRAG_ADMIN_PASSWORD` before starting FastAPI and open [the evidence admin](http://127.0.0.1:8765/admin). The username defaults to `admin` and can be set with `AGRIRAG_ADMIN_USER`. Use HTTPS when serving outside loopback.

Upload a PDF or UTF-8 text document to create a draft. Open the publisher’s original or download the stored copy, complete the source metadata, and record which passages you checked. Include only the passages to publish. For a scan, mixed-column table, or legacy Telugu encoding, use the rendered original to type or correct the passage and record the locator. Publishing locks the version. Upload a replacement as a new version, then archive the old one and select its successor.

`GET /api/evidence?state_id=andhra-pradesh&district_id=krishna&on_date=2026-11-24` returns approved passages for an exact district and date. `covered` indicates that both reviewed paddy guidance and weather evidence apply to that date. The endpoint excludes archived and undated material from the dated lookup.

## Pilot evidence

The initial evidence covers selected paddy decisions from 31 October to 4 November 2026. It includes drainage during rain, post-rain spray timing, and dry storage of harvested rice. Irrigation timing and water depth require additional applicable evidence. The app uses curated bulletins and has no automatic weather or advisory feed. The app reports a coverage gap if the selected date, district, crop stage, or topic lacks applicable evidence. Historical results display an archive label. IMD may replace the two generic PDF URLs with newer documents, so citations include the issue date and section.

## Extend coverage

1. Add the state and its district IDs and display names in [`dist/coverage.json`](dist/coverage.json). Each district has an `enabled` flag. The farmer form, API, and archive use this file.
2. Add official sources and evidence records in [`dist/evidence.mjs`](dist/evidence.mjs). Preserve source document dates, district-specific section locators, and validity windows. Use a dated source URL when one is available. Store the actual districts named in each source. Treat forecast dates as the local start date of the forecast period and retain the period details in the evidence text when relevant.
3. Add the English, Hindi, and Telugu summaries. Confirm the summaries and their scope against the original bulletin before marking a record `approved` for app use. Record the crop, stage, topic, and required weather event for each advisory. Weather entries use district scope and event tags.
4. Run the tests and verify at least one match and one coverage gap for the new district. The retrieval engine applies the same filters to every state.
