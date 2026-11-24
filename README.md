# AgriRAG

AgriRAG answers questions about weather, crop practices, and field decisions in English, Telugu, and Hindi. Its location catalog includes 783 district entries across India's 36 states and Union Territories. Crop advice has narrower evidence coverage. The starter catalog includes paddy guidance for Krishna and West Godavari, tomato, Bellary onion, okra, and brinjal practices for Tamil Nadu, and organic chilli guidance for Uttarakhand. It also supports general irrigation definitions from a national source.

## Run locally

From this folder, install the server dependencies and start FastAPI.

```sh
python -m pip install -r requirements.txt
python evidence_seed.py
python evidence_index.py --download-model
python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

Open the [farmer interface](http://127.0.0.1:8765). The form and results are available in English, Telugu, and Hindi. Choose **General farming** to ask a question without selecting a location. Try “Why are my tomato leaves turning yellow?” for a cited explanation of signs to check and precautions if there are leaf spots. Choose **Local crop & weather** for a district forecast or a field decision. Select a state or Union Territory, district, and optionally a date. A forecast-only question can leave the crop blank.

After choosing a state in the local mode, the crop menu lists crops with approved guidance somewhere in that state. Choosing a district narrows the menu to guidance for that district and applicable statewide sources. The menu includes dated editions so older questions can still be replayed. The coverage panel and advisory check the specific date, crop stage, and question.

The stage menus include germination and establishment where applicable, panicle initiation for paddy, and crop-specific stages such as bulb formation, tuber growth, head and curd formation, and pod filling. Existing stage IDs remain valid. [Examples of crop growth stages in IMD agromet bulletins](https://www.agritech.tnau.ac.in/pdf/2013/Bulletin_27.09.2013.pdf)

For internal testing, set `AGRIRAG_ENABLE_DEMOS=1` before starting the app to enable the original pilot lookup at `/archive/` and the mock API fixtures. Leave it disabled in deployed environments. The dated smoke test uses actual reviewed evidence and works with demos disabled.

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

Get state, district, crop, and stage IDs from `GET /api/farm-config`. The API rejects a mismatched state and district or a stage outside the selected crop. The response puts direct factual answers in `answer` with `answer_type: "information"`. The existing `suggested_action` field still supplies the primary text to older clients. The API returns `insufficient_evidence` when applicable evidence is unavailable and `conflicting_evidence` when applicable sources disagree. A retry with the same `Idempotency-Key` retains its advisory ID and rechecks evidence approval. A delivered live forecast retains its provenance snapshot for retries and language changes.

The farmer form uses `GET /api/coverage` before submission. Supply `state_id`, `district_id`, and optionally `crop`, `crop_stage`, and `on_date`. It checks today's reviewed coverage by default and reports whether a live lookup is configured. A live lookup can still fail when the farmer submits a question. Guidance may require a field observation or newer weather evidence for a particular decision.

The answer card puts citations beside each claim and shows the forecast used for a dated field decision separately. A paddy irrigation follow-up can be answered using the soil-moisture buttons or a field note, with the original question retained. If a reviewed source gives general irrigation guidance without a water quantity, the answer says so. The archived paddy harvest example shows maturity and storage-moisture thresholds. Tamil Nadu organic okra harvest guidance includes pod length, tenderness, and variety and market caveats. [TNAU okra harvest guide](https://agritech.tnau.ac.in/org_farm/orgfarm_bhendi_harvesting.html)

The server stores the original question and farm context in `data/advisories.sqlite3` by default. Set `AGRIRAG_DB_PATH` to use a different SQLite file.

Each supported result links its proposed action and explanation to the original passage IDs. Source cards show the publisher, issue date, original title, version, and PDF page or section. The server stores the exact response and source versions for each delivered advisory. The language switch translates the decision already displayed, with the same evidence IDs, validity, dates, and quantities. If the evidence changes, the interface asks the farmer to resubmit.

## Configure the model

AgriRAG supports the Gemini and OpenAI APIs for structured rendering. For Docker, copy `.env.example` to `.env` if it does not already exist. Fill in `GEMINI_API_KEY` and run `docker compose up -d --build`. Gemini takes priority when both keys are configured. For native Uvicorn, export the variables in its launching shell. [Gemini 3.1 Flash-Lite](https://aistudio.google.com/docs/models/gemini-3.1-flash-lite)

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Server-side Gemini credential |
| `AGRIRAG_GEMINI_MODEL` | Optional Gemini model override. Defaults to `gemini-3.1-flash-lite`. |
| `OPENAI_API_KEY` | Server-side OpenAI credential |
| `AGRIRAG_OPENAI_MODEL` | Optional OpenAI model override. Defaults to `gpt-4.1-mini`. |
| `AGRIRAG_LLM_TIMEOUT` | Request timeout in seconds, defaults to 20 |

The selected provider receives the question, farm context, and eligible passages for covered requests. AgriRAG validates the generated wording and citations before display. The app uses its cited verified templates when a key is absent, the provider fails, or the output fails validation. When the provider returns HTTP 429, the API records `generation_outcome: "provider_limit"` and the result shows a localized usage-limit notice alongside the verified answer. The historical Qwen report applies to its recorded model and fixtures.

## Verify live weather in Postman

The Docker image and Compose enable live weather by default. Set `AGRIRAG_LIVE_WEATHER=0` to disable it. For native Uvicorn, export `AGRIRAG_LIVE_WEATHER=1`. The public [Open-Meteo forecast endpoint](https://open-meteo.com/en/docs) is available for non-commercial use. Set `OPEN_METEO_API_KEY` for the licensed customer endpoint. The backend validates the requested day in Asia/Kolkata, units, and forecast values, and can fetch today through six days ahead. The result cites a representative point and records the retrieval time with the forecast. The district outlook reports the daily mean surface soil moisture when all 24 hourly values for the top 0–1 cm are available. The API field `soil_moisture_m3_m3` is volumetric and the interface expresses it as a percentage. Paddy irrigation decisions still use an observation from the field.

Use Postman to send `POST http://127.0.0.1:8765/api/advisories` with `Content-Type: application/json`. This example requires no crop stage or farmer observation.

```json
{
  "state_id": "maharashtra",
  "district_id": "lgd-490",
  "question": "What is the weather tomorrow?",
  "language": "en"
}
```

Verify `status: "supported"`, `answer_type: "information"`, the local `requested_date`, the values in `weather_snapshot`, and an Open-Meteo citation. Check that a different district produces a different requested point. For a general question, POST `{"question_type":"general","question":"Why are my tomato leaves turning yellow?","language":"en"}` to the same endpoint without a location. Check the symptom explanation and leaf-spot precautions against their separate citations. To try local vegetable guidance, select Coimbatore (`tamil-nadu`, `lgd-569`), choose Tomato, and ask “How should I irrigate my tomatoes?”

Open **District forecast** in the farmer interface to compare 3, 5, or 7 days. This calls `GET /api/forecast?state_id=maharashtra&district_id=lgd-490&days=5`, also usable in Postman. A window starts today in Asia/Kolkata unless `start_date` is supplied. Each day shows reviewed district rainfall when available and live temperature and wind for the district's reference point. If reviewed rainfall is unavailable, a validated live value can be shown. Conflicting or unavailable rainfall is flagged. Multi-day outlooks are for planning. Crop decisions continue to use evidence for the specific requested date. [Open-Meteo forecast documentation](https://open-meteo.com/en/docs)

## Prepare the evidence index

From the project folder, load the reviewed catalog and build Chroma's local vector index.

```sh
python evidence_seed.py
python evidence_index.py --download-model
```

The index uses the pinned multilingual E5-small ONNX model on CPU. The setup command verifies the downloaded model and tokenizer checksums. The model files default to `data/e5-small` and the Chroma directory defaults to the SQLite path with a `.chroma` suffix. Set `AGRIRAG_E5_DIR` or `AGRIRAG_CHROMA_PATH` to change those paths. Advisory requests run locally after setup and index newly published candidates as needed.

SQLite supplies the eligible reviewed passage IDs and citation metadata. Chroma ranks only those passages for the requested topic. The backend separately validates live forecasts for the configured district point and date. General crop guidance can apply at state scope when its source supports that scope. The rules use reviewer-selected stage and decision codes. A more specific applicable scope takes precedence, and a newer applicable edition of the same publication replaces its older edition. Incomparable conflicting sources are cited and the system withholds an action.

Set `AGRIRAG_EVIDENCE_MODE=sqlite` on memory-constrained hosts. Startup skips the embedding model download and Chroma initialization. The app uses the full set of SQLite candidates with the same topic, district, crop, stage, approval, date and conflict checks, ordering applicable passages by ID instead of semantic relevance. Render defaults to `sqlite`, and other hosts default to `chroma`. Set `AGRIRAG_EVIDENCE_MODE=chroma` explicitly on a Render instance with sufficient memory if you want semantic ranking.

## Verify

Run `node --test` to verify the archive retrieval, or install the API test dependencies and run the Python suite. The real multilingual ranking test runs when the E5 model is installed.

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s test -p "test_*.py"
```

## Evidence review

The [pilot audit](EVIDENCE_AUDIT.md) records the reviewed districts, source editions, supported uses, and coverage window. Load the approved passages into the local SQLite database with `python evidence_seed.py`. If you have the three original PDFs listed in `pilot_evidence.json`, supply their directory with `--snapshots`. The importer checks every file against the audited SHA-256 before attaching it. Re-running the seed preserves existing records, including archived versions.

Set `AGRIRAG_ADMIN_PASSWORD` before starting FastAPI and open [the evidence admin](http://127.0.0.1:8765/admin). The username defaults to `admin` and can be set with `AGRIRAG_ADMIN_USER`. Use HTTPS when serving outside loopback.

Under **Advisory feedback**, reviewers can inspect Useful, Unclear, and Potentially incorrect ratings alongside the original question, shown answer, language, and exact evidence versions.

Under **Evidence maintenance**, review district forecasts that have expired or end in the next seven days, approved editions missing an original copy, and grouped requests that still had an evidence gap on their latest submission over the past 30 days. The report excludes demo sessions and omits question text. For a weekly check, run `python evidence_maintenance.py report` or use the protected page. Compare the issue date, edition, district rows, crop stages, and validity against the publisher, then upload and review each new edition as a draft. Preserve existing archived editions. With a known audited digest, `python evidence_maintenance.py attach-snapshot SOURCE_ID PATH` attaches exact bytes to an existing approved or archived edition without changing its approval. [IMD district bulletin archive](https://mausam.imd.gov.in/responsive/agromet_adv_ser_district_past_en.php)

The same maintenance page lists every configured district and separates district-specific crop guidance, applicable statewide guidance, and reviewed district rainfall. Run `python evidence_maintenance.py report --date 2026-11-24` to reproduce the dated national baseline as JSON. The report also records which districts have coordinates for optional live weather. [Nationwide baseline and source audit](EVIDENCE_AUDIT.md#nationwide-coverage-baseline)

Upload a PDF or UTF-8 text document to create a draft. Open the publisher’s original or download the stored copy, complete the source metadata, and record which passages you checked. Include only the passages to publish. For a scan, mixed-column table, or legacy Telugu encoding, use the rendered original to type or correct the passage and record the locator. Publishing locks the version. Upload a replacement as a new version, then archive the old one and select its successor.

For use by the decision engine, record the stated crop stage and map it to a supported farmer-form stage. Select a decision code only when the passage supports that action. For rainfall, record the verified daily values in millimetres keyed by ISO date on a `district-rainfall-forecast` weather passage. Mark a passage statewide only when the publication explicitly supports that scope.

`GET /api/evidence?state_id=andhra-pradesh&district_id=krishna&on_date=2026-11-24` returns approved passages for an exact district and date. `covered` indicates that both reviewed paddy guidance and weather evidence apply to that date. The endpoint excludes archived and undated material from the dated lookup.

## Deploy and smoke-test

1. Set the admin password and provider credentials in your host's secret configuration. Set `AGRIRAG_GEMINI_MODEL` explicitly to the model you tested. Use `AGRIRAG_DATA_DIR` to point to a persistent directory outside the release checkout. Keep one application instance per SQLite and Chroma volume.
2. Run `docker compose up -d --build --wait --wait-timeout 300`. Compose binds to loopback on port 8765 by default. Put a TLS reverse proxy on the same host in front of it. Restrict access to `/admin` and `/api/admin/*` to staff, and apply request rate limits to advisory, forecast, and login traffic at the proxy. Allow outbound HTTPS to the model and weather providers and to Hugging Face for first-time model setup. The Docker readiness check uses `/readyz` to check the evidence database, model files, and Chroma collection. `/healthz` checks that the web process is responding.
3. Back up the data directory with the app stopped to capture a consistent copy. It contains the SQLite catalog, source snapshots, advisory and feedback logs, Chroma, and E5 weights. Store backups with restricted access. To test recovery, use a copy in a separate data directory, start a separate Compose project on an unused port, and rerun the smoke test. The seed and indexing commands run on startup and preserve existing published and archived source versions.

Run `python demo/run.py` against the running service. It replays the 24 November 2026 scenario with the two pilot districts, checks missing archived coverage, and compares equivalent English, Telugu, and Hindi answers. Use `--url` for a different deployment. Add `--smoke` with admin credentials set to submit test feedback and verify the protected admin view. See the [manual demo](demo/README.md), [language verification record](demo/VERIFICATION.md), and [farmer pilot plan](demo/PILOT.md).

For a Render Free test deployment, use Docker, leave the root directory and start command at their defaults, and set the health check path to `/readyz`. The app detects Render using its runtime environment and starts in SQLite mode unless explicitly overridden. Keep Gemini credentials as runtime environment variables. Render Free recreates local state after restarts, so use test data only. [Render environment variables](https://render.com/docs/environment-variables) · [Render Free service limits](https://render.com/docs/free)

Before a farmer pilot, name an evidence reviewer and confirm current advisories for the supported districts. Farmer questions and observations are stored for session continuity and sent to the configured model provider on supported requests. Set and communicate your retention policy before collecting real farmer data.

### Render backend with a Vercel frontend

1. Deploy the Docker service on Render and verify that its public HTTPS URL returns `{"status":"ready"}` at `/readyz`. Configure Gemini, live weather, and the admin password in Render.
2. Import this repository and the `main` branch on Vercel. Leave the root directory at `./` and select **Other** as the framework preset. Use the repository build configuration. Vercel publishes the static farmer interface and forwards its advisory, forecast, coverage, and feedback requests to `https://krishirag.onrender.com`. Set `RENDER_BACKEND_URL` only if using a different Render HTTPS origin.
3. Deploy and test `/api/farm-config` on the Vercel domain, then submit a question and feedback. Open `/admin` on the Render domain for evidence and feedback review.

## Evaluate

Run `python evaluation/run.py --templates-only` for a credential-free baseline. With `GEMINI_API_KEY` or `OPENAI_API_KEY` exported, run `python evaluation/run.py` for LLM alone, basic RAG, checked RAG, and verified templates. The default output is `data/evaluation-results.json`. The 27 scenario families each have English, Telugu, and Hindi variants. They include clarification, date and district restrictions, vegetable guidance, direct answers, and a fixed weather response replayed across the India date boundary. See the [historical comparison and new baseline](evaluation/REPORT.md) and [expansion cases](evaluation/expansion_cases.json).

The runner records output acceptance, fallback, latency, and the token usage reported by the provider. Pass `--input-usd-per-million` and `--output-usd-per-million` together to estimate cost using the rates for the configured model. The estimate bills all reported input tokens at the supplied input rate and may differ from the invoice.

## Pilot evidence

The original Andhra Pradesh archive covers selected paddy decisions from 31 October to 4 November 2026. The FastAPI replay uses later reviewed sources listed in `pilot_evidence.json`. IMD can replace material at generic PDF URLs, so citations retain the issue date and section. Expansion sources in `expansion_evidence.json` preserve the exact geographic and crop scope of each reviewed section.

## Extend coverage

The farmer catalog in `india_districts.json` uses the November 2026 [bharatlas LGD crosswalk](https://bharatlas.com/releases/bharatlas-cw-2026.11/) (CC0/CC BY 4.0). It drops rows without a current LGD identifier and deduplicates by LGD ID. Forecast points are derived from [LGD/Bharatmaps district boundaries compiled by ramSeraph](https://github.com/ramSeraph/indian_admin_boundaries/releases/tag/districts) (CC0). Each point is inside the largest polygon for its matched district and rounded to four decimal places. These are reference points. Use stable LGD codes when updating the catalog and preserve the legacy pilot IDs in `locations.py`. The original archive has separate static coverage in `dist/coverage.json`.

Use the protected admin workflow to publish crop guidance. Capture the source URL, district or approved statewide scope, crop, stage, date limits, and exact locator. Check that a question in coverage returns a cited answer and that the same question outside its scope withholds an action.

## Recommended next tasks

1. Use the maintenance report to prioritize reviewing tomato, chilli, and onion irrigation guidance from relevant state universities and KVKs.
2. Add opt-in farm coordinates, short forecast caching, and provider outage monitoring. Evaluate field-point forecasts against IMD where they overlap.
3. Expand reviewed direct questions and answer templates, including soil, crop stages, and harvest information. Have fluent Telugu and Hindi reviewers check wording against the source.
4. Rerun the labeled evaluation with OpenAI and add cases for nationwide district selection, live dates, vegetables, and direct answers. Publish measured citation support, coverage, latency, and cost.
