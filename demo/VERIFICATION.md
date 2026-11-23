# Three-language verification

| Check | English | Telugu | Hindi |
| --- | --- | --- | --- |
| Farmer form and required-field validation | Browser checked | Browser checked | Browser checked |
| Question, crop-stage follow-up, cited result, and saved feedback | Browser completed | Browser completed | Browser completed |
| Same decision, forecast quantity, dates, caveats and source references for the archived replay | API compared | API compared | API compared |
| Localized evidence-gap result and requested date | API checked | API checked | Browser checked |
| Loading and retry after a failed request | DOM test verified loading announcement, disabled submit, localized retry, and retained question | Same check passed | Same check passed |

Browser verification used a 360 CSS-pixel iframe. The Telugu and Devanagari result screens rendered with self-hosted Noto fonts, and both had a 345-pixel content viewport with no horizontal overflow. I checked wrapped explanation, source, and validity text visually. The 15-pixel difference was the iframe scrollbar.

The same 24 November 2026 Krishna case was also checked through the running FastAPI service. The language change retained the decision code, 1 mm district forecast, requested date, validity range, and cited passage IDs. The protected admin endpoint returned the question, delivered response, language and source versions for each rating. Those ratings remained available after restarting FastAPI with the same SQLite file. A separate live-provider HTTP request returned accepted model claims citing versions 93/2026 and 94/2026.

No independent fluent reviewer was available. The Telugu and Hindi copy was tested in the interface and compared against the approved action templates, but has not received independent linguistic sign-off.
