# Olist Marketplace Data Quality & Decision-Ready Analytics System
**Marketplace Health: Delivery, Concentration, and Retention on a Verified Data Layer**

An end-to-end business-analytics project on the **Olist Brazilian e-commerce** dataset (9 tables, ~100k orders, 2016–2018). It rebuilds the data at the correct grain, answers four decision questions, and ships a professional analyst report — with an **auditable AI step** that classifies and validates customer-review topics.

> **Thesis:** a dashboard is only as useful as the data behind it. The same dataset yields *different* headline numbers depending on whether the join grain, geolocation duplication, and customer identity are fixed first. This project fixes them, shows the wrong-vs-right numbers, and builds every finding on the corrected layer.

## Business problem

Where should the Olist marketplace focus to protect revenue and customer satisfaction — and is the underlying data trustworthy enough to act on those numbers? Specifically: (a) what is associated with low review scores, (b) where revenue concentrates, (c) how the marketplace retains customers, and (d) which headline numbers change once the data is decision-ready.

## Headline Results

| Question | Finding |
|---|---|
| What is associated with low scores? | Delivery time is strongly associated with lower review scores: average delivery time rises from about 11 days for 5-star reviews to about 21 days for 1-star reviews. |
| Where does revenue concentrate? | 18 of 74 product categories generate about 80% of revenue; São Paulo contributes about 38% of revenue; the top 3 states contribute about 63%. |
| How well does the marketplace retain customers? | Only 3.12% of customers reorder, suggesting the marketplace behaves more like an acquisition-driven system than a retention-driven system. |
| What changes after cleaning? | A naive multi-table join inflates product revenue by about 4.5% and cash collected by about 27%; the corrected GMV is R$13.59M and net revenue is R$13.22M. |
| What do customers complain about? | Negative reviews are concentrated around product quality and delivery issues; delivery-related complaints are associated with substantially slower orders. |

## Data-quality framework — the three engineering hazards

1. **Join fan-out / double-counting** — 9,803 orders have multiple items (max 21) and 2,961 have multiple payments (max 29). A naive `orders × items × payments` join multiplies rows. *Fix:* aggregate items and payments to **order grain** before joining.
2. **Geolocation duplication** — 1,000,163 rows for only 19,015 zip prefixes (~53×). *Fix:* dedupe to one row per prefix.
3. **Customer identity** — 99,441 `customer_id` collapse to 96,096 `customer_unique_id` (a new id per order). *Fix:* key RFM and repeat rate on `customer_unique_id`.

Full register (10 issues + referential-integrity checks) in [`documentation/qa_tracker.csv`](documentation/qa_tracker.csv).

## The AI-augmented step (validated, not hand-waved)

A large language model (Claude) classifies a reproducible random sample of **1,000** Portuguese reviews by **topic** (delivery / product / price / service / other) and **sentiment**, reading text only. Validation:

- **Inter-annotator agreement** vs a *second, independent* LLM annotator (Claude) (blind to the first labels) on a 200-review gold set: topic **κ = 0.81** (86.5%), sentiment **κ = 0.89** (94%).
- **External validity** — text sentiment matches the star rating (which the model never saw) on **83%** of reviews: mean stars 1.8 (neg) / 3.9 (neu) / 4.8 (pos).
- **Triangulation** — delivery complaints concentrate in slow, low-scoring orders, tying the text back to the structured r = −0.33 signal.

Detail in [`ai/validation_report.md`](ai/validation_report.md).

## Repository map

```
README.md                      this file
requirements.txt
analysis.ipynb                 START HERE — narrative walkthrough: clean -> signal -> 3 hazards -> 8 inline figures -> AI step
build_pipeline.py              headless re-run of the notebook's pipeline (raw -> cleaned -> output)
data/
  raw/        Placeholder only (.gitkeep). Raw Kaggle CSVs are NOT committed — download from Kaggle (see below).
  cleaned/    Placeholder only (.gitkeep). Row-level cleaned tables are regenerated locally and NOT committed.
  output/     Committed dashboard-ready aggregate tables generated from the pipeline  <- point Tableau here
sql/          profile_checks.sql · business_questions.sql · dashboard_tables.sql  (DuckDB)
scripts/      step0_audit · run_sql · ai_sample · ai_validate · build_report · make_docs
documentation/ data_dictionary.csv · qa_tracker.csv · methodology_notes.md · step0_audit.md
ai/           labels + review_classification.csv + validation_report.md
reports/
  Olist_Analyst_Report.docx    the full analyst report (embedded figures + SAS framework + analysis)
  charts/                      8 figure PNGs
```

## Data & license

Olist Brazilian E-Commerce Public Dataset, via Kaggle: `olistbr/brazilian-ecommerce` (**CC BY-NC 4.0** — attribution, non-commercial; fine for a portfolio with credit). Real commercial data, anonymized; company/partner names in review text were replaced with Game-of-Thrones house names — treat the text as real customer language but those names are not real brands.

**The raw CSVs are not committed** (`.gitignore` excludes `data/raw/*.csv`). To reproduce, download the dataset from Kaggle and place the nine CSVs in `data/raw/`.

## How to run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 0. download the 9 Olist CSVs from Kaggle into data/raw/ first (see "Data & license")

# 1. MAIN — open the narrative notebook and Run All:
#    signal check -> clean at the correct grain -> data/output tables -> all 8 figures inline
jupyter notebook analysis.ipynb

# 2. AI review classification + validation (regenerates ai/ outputs; optional — outputs are committed)
python scripts/ai_sample.py          # draw the reproducible review sample
python scripts/ai_validate.py        # inter-annotator + external validation, triangulation

# 3. build the Word report from data/output/ + reports/charts/
python scripts/build_report.py       # -> reports/Olist_Analyst_Report.docx

# optional helpers
python scripts/step0_audit.py        # profile all 9 tables + reconcile 37 figures -> documentation/step0_audit.md
python build_pipeline.py             # headless re-run of the notebook's clean -> output pipeline
python scripts/run_sql.py            # DuckDB SQL cross-checks
python scripts/make_docs.py          # regenerate the technical schema baseline (needs raw data; will NOT overwrite the curated dictionary/tracker)
```

## Key outputs

- **`reports/Olist_Analyst_Report.docx`** — the analyst report (Times New Roman 12pt, SAS figure framework, modules A/C/B).
- **`data/output/*.csv`** — Tableau-ready aggregates (the dashboard's source of truth).
- **`ai/`** — review classification + validation report.
- **`documentation/`** — data dictionary, QA tracker, methodology notes.

*Tableau is built separately from `data/output/`; the report is the deliverable of this repository.*

## Tech stack

Python (pandas, numpy, matplotlib, python-docx), DuckDB (SQL cross-checks), Claude (review classification + validation). Built and documented as reproducible Python + SQL, with an AI-assisted review-classification step (Claude).
