# AgriRAG

AgriRAG is an evidence-grounded paddy advisory app. The Andhra Pradesh pilot covers Krishna and West Godavari. Both districts have paddy guidance from AMFU Guntur in [IMD Agromet Bulletin 87/2026](https://mausam.imd.gov.in/visakhapatnam/mcdata/APAgromet.pdf) and named rows in the [IMD Amaravati district forecast](https://mausam.imd.gov.in/amaravati/mcdata/District_Forecast.pdf).

## Run locally

From this folder, install the server dependencies and start FastAPI.

```sh
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

Open the [farmer interface](http://127.0.0.1:8765). It uses plain HTML, CSS, and JavaScript without a build step or API key. The form and its results are available in English, Telugu, and Hindi. The default mode uses reviewed evidence. The scenario selector still offers labeled demo examples.

Open the [evidence archive](http://127.0.0.1:8765/archive/) for the dated lookup. Choose **View archived advisory** to load an example for Krishna on 3 November 2026. The demo and the archive share the state and district configuration. Set `placeholder: true` on a district to label it as a demo district in the farmer interface.

## Advisory API

Open the [API documentation](http://127.0.0.1:8765/docs) to try `POST /api/advisories`. For a new session, send a body like this.

```json
{
  "state_id": "andhra-pradesh",
  "district_id": "krishna",
  "crop": "paddy",
  "crop_stage": "unknown",
  "question": "Do I need to irrigate on 2026-11-24?",
  "language": "en"
}
```

When the response asks for the crop stage, send `session_id` from the response and `crop_stage`, such as `grain-filling`. When it asks about field conditions, send `session_id` and `field_observations`, such as “Standing water” or “The soil is drying.” Relative dates are interpreted in Asia/Kolkata and kept with the original question across follow-ups. An optional `requested_date` on a new session takes precedence over the question date. A follow-up can set `language` to `en`, `te`, or `hi`. To ask a new question, omit `session_id`.

For a specific demo, add `demo_scenario` when starting the session. The available values are `supported`, `conditional`, `clarification`, `coverageGap`, and `conflict`. In evidence mode, the API returns `insufficient_evidence` for unsupported locations or unavailable evidence and `conflicting_evidence` when applicable sources disagree. An exact retry with `Idempotency-Key` retains its advisory ID and rechecks current evidence approval.

The server stores the original question and farm context in `data/advisories.sqlite3` by default. Set `AGRIRAG_DB_PATH` to use a different SQLite file.

## Prepare the evidence index

From the project folder, load the reviewed catalog and build Chroma's local vector index.

```sh
python evidence_seed.py
python evidence_index.py --download-model
```

The index uses the pinned multilingual E5-small ONNX model on CPU. The setup command verifies the downloaded model and tokenizer checksums. The model files default to `data/e5-small` and the Chroma directory defaults to the SQLite path with a `.chroma` suffix. Set `AGRIRAG_E5_DIR` or `AGRIRAG_CHROMA_PATH` to change those paths. Advisory requests run locally after setup and index newly published candidates as needed.

SQLite supplies the eligible passage IDs and the citation metadata. Chroma ranks only those IDs for the requested topic. Dated weather decisions require an exact district and a reviewed forecast value for that date. General crop guidance can apply at state scope when the reviewer has explicitly verified that scope. The rules use reviewer-selected stage and decision codes such as `grain-filling` and `maintain_moisture`. A more specific applicable scope takes precedence, and a newer applicable edition of the same publication replaces its older edition. Incomparable conflicting sources are cited and the system withholds an action.

## Verify

Run `node --test` to verify the archive retrieval, or install the API test dependencies and run the Python suite. The real multilingual ranking test runs when the E5 model is installed.

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s test -p "test_*.py"
```

## Evidence review

The [pilot audit](EVIDENCE_AUDIT.md) records the reviewed districts, source editions, supported uses, and coverage window. Load the approved passages into the local SQLite database with `python evidence_seed.py`. If you have the three original PDFs listed in `pilot_evidence.json`, supply their directory with `--snapshots`. The importer checks every file against the audited SHA-256 before attaching it. Re-running the seed preserves existing records, including archived versions.

Set `AGRIRAG_ADMIN_PASSWORD` before starting FastAPI and open [the evidence admin](http://127.0.0.1:8765/admin). The username defaults to `admin` and can be set with `AGRIRAG_ADMIN_USER`. Use HTTPS when serving outside loopback.

Upload a PDF or UTF-8 text document to create a draft. Open the publisher’s original or download the stored copy, complete the source metadata, and record which passages you checked. Include only the passages to publish. For a scan, mixed-column table, or legacy Telugu encoding, use the rendered original to type or correct the passage and record the locator. Publishing locks the version. Upload a replacement as a new version, then archive the old one and select its successor.

For use by the decision engine, record the stated crop stage and map it to a supported farmer-form stage. Select a decision code only when the passage supports that action. For rainfall, record the verified daily values in millimetres keyed by ISO date on a `district-rainfall-forecast` weather passage. Mark a passage statewide only when the publication explicitly supports that scope.

`GET /api/evidence?state_id=andhra-pradesh&district_id=krishna&on_date=2026-11-24` returns approved passages for an exact district and date. `covered` indicates that both reviewed paddy guidance and weather evidence apply to that date. The endpoint excludes archived and undated material from the dated lookup.

## Pilot evidence

The initial evidence covers selected paddy decisions from 31 October to 4 November 2026. It includes drainage during rain, post-rain spray timing, and dry storage of harvested rice. Irrigation timing and water depth require additional applicable evidence. The app uses curated bulletins and has no automatic weather or advisory feed. The app reports a coverage gap if the selected date, district, crop stage, or topic lacks applicable evidence. Historical results display an archive label. IMD may replace the two generic PDF URLs with newer documents, so citations include the issue date and section.

## Extend coverage

1. Add the state and its district IDs and display names in [`dist/coverage.json`](dist/coverage.json). Each district has an `enabled` flag. The farmer form, API, and archive use this file.
2. Add official sources and evidence records in [`dist/evidence.mjs`](dist/evidence.mjs). Preserve source document dates, district-specific section locators, and validity windows. Use a dated source URL when one is available. Store the actual districts named in each source. Treat forecast dates as the local start date of the forecast period and retain the period details in the evidence text when relevant.
3. Add the English, Hindi, and Telugu summaries. Confirm the summaries and their scope against the original bulletin before marking a record `approved` for app use. Record the crop, stage, topic, and required weather event for each advisory. Weather entries use district scope and event tags.
4. Run the tests and verify at least one match and one coverage gap for the new district. The retrieval engine applies the same filters to every state.
