# Measured advisory evaluation

Run on 23 November 2026 against **Qwen2.5-0.5B-Instruct Q4_0** served by llama.cpp b10927 on Windows CPU with five inference threads. The fixed [evaluation set](cases.json) has 20 scenario families, each in English, Telugu, and Hindi. All 60 cases ran in each of the three modes, for 180 recorded runs. [Raw results](results.json)

| Metric | LLM alone | Basic RAG | RAG with applicability checks |
| --- | ---: | ---: | ---: |
| Correct recommendation on cases that warranted one | 0 / 18 | 0 / 18 | 18 / 18 |
| Fully supported citations on issued recommendations | —, 0 issued | —, 0 issued | 18 / 18 |
| Correct clarification or withholding | 27 / 42 | 18 / 42 | 42 / 42 |
| Answer coverage | 0 / 60 | 0 / 60 | 18 / 60 |
| Agreement across all three languages | 2 / 20 | 3 / 20 | 20 / 20 |
| Median response time, all cases | 3,853 ms | 7,405 ms | 20 ms |
| Median response time, cases that warranted an answer | 4,645 ms | 7,459 ms | 15,628 ms |
| Invalid or timed-out outputs reaching the evaluator | 0 | 19 | 0 |

The baselines received identical questions, farm context, and model settings. LLM alone received no passages. Basic RAG received the top three semantic matches from the same trial catalog without applicability filtering. Checked RAG applied the production rules, passing only a verified decision and its applicable passages to the same model for wording. The checked renderer had a larger output budget because it returned localized sentences and per-claim citations. All modes ran sequentially on the same local provider, with an 18-second provider timeout. Timing includes retrieval and model calls where used. The checked mode skipped the model on 42 system decisions, which explains the difference between its two latency medians.

Recommendation correctness checks the labeled decision code and the expected rainfall amount when the case specifies one. Citation support requires the exact reviewed passage set for an issued answer. Clarification or withholding checks the status and the targeted field, when applicable. Language agreement compares status, action, follow-up field, citations, and numerical rainfall across the three variants. Zero issued answers leaves the baselines without a citation-support denominator.

## Representative failures

- **Krishna, missing field moisture.** LLM alone returned insufficient evidence. Basic RAG also withheld and listed passages from both districts plus the university background passage. Checked RAG asked whether water was standing or the soil had started drying.
- **West Godavari rainfall in English.** Basic RAG returned insufficient evidence even with both districts' forecast passages in its retrieved set. Checked RAG used the West Godavari row and reported the reviewed **1.9 mm** forecast for 24 November.
- **Contradictory sources.** For the Telugu Krishna rainfall conflict, basic RAG timed out. In the separate irrigation conflict, LLM alone withheld without identifying the disagreement. Checked RAG returned conflicting evidence and cited the disagreeing passages. The evaluation-only conflicting sources are synthetic and never enter the pilot catalog.

## Interpretation

The checks improved decision coverage and distinguished missing context from evidence gaps and conflicts in this labeled pilot. The local model supplied accepted wording for **1 of 18** supported cases. The other 17 used cited templates after **9 validation failures and 8 provider errors**. The measured correctness comes primarily from the decision rules, evidence checks, and fallback. No Telugu or Hindi model wording passed validation in this run.

Basic RAG produced 18 schema-validation failures and one timeout. These results apply to this model, prompt, fixtures, and hardware. The evaluation uses developer-authored labels on a small repeatable acceptance set. An independent agronomic or linguistic reviewer has not reviewed the labels.

## Expanded template baseline, 23 November 2026

I ran `python evaluation/run.py --templates-only --output data/evaluation-templates-81.json` with the original 60 cases and [21 expansion cases](expansion_cases.json). This run used the local evidence index and verified templates.

| Metric | Verified templates |
| --- | ---: |
| Correct decision or information on cases that warranted an answer | 33 / 33 |
| Exact expected citations on issued answers | 33 / 33 |
| Correct clarification or withholding | 48 / 48 |
| Answer coverage | 33 / 81 |
| Agreement across all three languages | 27 / 27 scenario families |
| Median response time | 24.1 ms |
| Median issued answer time | 29.0 ms |

The weather replay used a fixed synthetic forecast and a clock set near midnight in Asia/Kolkata. The timer includes local retrieval and response construction. OpenAI measurements are pending an API credential. The older Qwen results above apply to the original corpus and its previous implementation.
