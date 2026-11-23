# AgriRAG

AgriRAG is an evidence-grounded paddy advisory app. The Andhra Pradesh pilot covers Krishna and West Godavari. Both districts have paddy guidance from AMFU Guntur in [IMD Agromet Bulletin 87/2026](https://mausam.imd.gov.in/visakhapatnam/mcdata/APAgromet.pdf) and named rows in the [IMD Amaravati district forecast](https://mausam.imd.gov.in/amaravati/mcdata/District_Forecast.pdf).

## Run locally

From this folder, run `python -m http.server 8765 --bind 127.0.0.1 --directory dist` and open [AgriRAG](http://127.0.0.1:8765). The app has no build dependencies or API keys. Serve the `dist` directory to host it.

Select a state, district, crop stage, topic, and field operation date. Answer language is independent of location. Choose **View archived advisory** to load an example for Krishna on 3 November 2026 in the selected language.

Run `node --test` from the project folder to verify retrieval.

## Pilot evidence

The initial evidence covers selected paddy decisions from 31 October to 4 November 2026. It includes drainage during rain, post-rain spray timing, and dry storage of harvested rice. Irrigation timing and water depth require additional applicable evidence. The app uses curated bulletins and has no automatic weather or advisory feed. The app reports a coverage gap if the selected date, district, crop stage, or topic lacks applicable evidence. Historical results display an archive label. IMD may replace the two generic PDF URLs with newer documents, so citations include the issue date and section.

## Extend coverage

1. Add the state and its district IDs and display names in [`dist/coverage.mjs`](dist/coverage.mjs). Each district has an `enabled` flag.
2. Add official sources and evidence records in [`dist/evidence.mjs`](dist/evidence.mjs). Preserve source document dates, district-specific section locators, and validity windows. Use a dated source URL when one is available. Store the actual districts named in each source. Treat forecast dates as the local start date of the forecast period and retain the period details in the evidence text when relevant.
3. Add the English, Hindi, and Telugu summaries. Confirm the summaries and their scope against the original bulletin before marking a record `approved` for app use. Record the crop, stage, topic, and required weather event for each advisory. Weather entries use district scope and event tags.
4. Run the tests and verify at least one match and one coverage gap for the new district. The retrieval engine applies the same filters to every state.
