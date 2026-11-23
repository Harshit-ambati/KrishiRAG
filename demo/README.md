# Andhra Pradesh advisory demo

All four scenarios replay a fixed pilot archive. The reference date is **24 November 2026** unless a scenario explicitly uses a different date. The replay uses the forecast values as issued in the cited bulletins.

Run `python demo/run.py` after starting FastAPI. Use `--url` to test a different deployment. To reproduce the same scenarios in the browser, leave **Use reviewed evidence** selected.

| Scenario | Form input | Expected result |
| --- | --- | --- |
| Supported paddy decision | Andhra Pradesh, Krishna, **Milk to grain hardening**. Question “Should I irrigate my paddy on 2026-11-24 if rain is expected?” Observation “The soil is drying.” | Maintain adequate moisture and avoid excess irrigation or standing water. Cite AMFU Guntur bulletin 93/2026, PDF page 21, for the action and Amaravati forecast 94/2026, page 1, for Krishna’s 1 mm forecast. |
| Missing stage | Repeat the first question and select **I’m not sure**. | Ask only for crop stage. Choose **Milk to grain hardening** and send the update to get the supported result. |
| Expired forecast | Krishna. Question “Will it rain on 2026-11-29?” | Insufficient evidence. The loaded district forecast ends 28 November. The API runner also checks Eluru, outside the enabled pilot. |
| Language consistency | Same location, stage and observation. Ask “2026-11-24 తేదీన వరి పొలానికి నీరు పెట్టాలా?” in Telugu or “2026-11-24 को क्या मुझे धान की सिंचाई करनी चाहिए?” in Hindi. | Same decision, 1 mm, date and two passage IDs. Switch language after answering to see the same saved decision with translated wording. |

For the district comparison, switch the first scenario to **West Godavari**. The crop guidance still supports the same action. The sources change to the West Godavari rice row on page 24 and the West Godavari forecast row on page 1. The reviewed forecast for that date is **1.9 mm**, compared with **1.0 mm** for Krishna. [Paddy guidance](https://mausam.imd.gov.in/visakhapatnam/mcdata/APAgromet.pdf) · [District forecast](https://mausam.imd.gov.in/amaravati/mcdata/APvaf.pdf)

With admin credentials configured, run `python demo/run.py --smoke` against a test database to submit ratings for all three languages. They appear under **Advisory feedback** at `/admin`.
