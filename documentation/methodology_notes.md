# Methodology Notes

Technical companion to the analyst report. Every number in the report and the output tables traces to the scripts below; nothing is hand-entered.

## 1. Pipeline (raw → cleaned → output)

`build_pipeline.py` reads `data/raw/*.csv` **read-only** and writes `data/cleaned/` and `data/output/`. Decisions:

- **Grain.** Items and payments are aggregated to **order grain** before any join, so revenue is never multiplied by the fan-out. Product revenue is computed from `order_items.price`; cash from `order_payments.payment_value`; they are kept separate.
- **Net vs gross.** GMV = Σ price over orders with items. Net product revenue = GMV restricted to `delivered` orders — the figure the dashboard should publish.
- **Geolocation dedupe.** `olist_geolocation` is reduced to one row per `zip_code_prefix` (mean lat/lng, modal city/state) via a vectorized mode. State-level revenue uses the `customers` table's `customer_state` directly, avoiding the geo join entirely.
- **Identity.** RFM and repeat rate are keyed on `customer_unique_id` (96,096 people) rather than `customer_id` (99,441 per-order keys). Reference date for recency = max purchase timestamp.
- **Category.** Portuguese categories are mapped to English via the translation table; the two untranslated categories (`pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`) get manual labels; 610 missing categories bucket to `unknown`.
- **Derived fields.** `delivery_days`, `is_late`, `delivered`, `order_value`, RFM scores, `review_has_text` — see `documentation/data_dictionary.csv`.

## 2. Verification (Step 0 + SQL)

- `scripts/step0_audit.py` profiles all nine tables and reconciles 37 figures against the documented expected values: order value vs payments **r = 1.000**; delivery_days vs review_score **r = −0.334**; GMV ≈ R$13.59M; Nov-2017 peak = 7,289 delivered orders. Output: `documentation/step0_audit.md`.
- `sql/` (DuckDB, run via `scripts/run_sql.py`) independently re-computes the same aggregates and runs referential-integrity anti-joins (**zero orphans** across items/payments/reviews vs orders, and items vs products). The SQL and the Python pipeline agree on every headline number — this cross-check is the reconciliation's backbone.

## 3. Metric definitions

See the KPI dictionary in the report and `data_dictionary.csv`. Key choices: revenue at order grain; "delivered" via `order_status`; on-time = delivered ≤ estimated; delivery metrics exclude orders without delivery dates; repeat = `customer_unique_id` with > 1 order.

## 4. AI review-classification protocol (DQ-10)

- **Classifier.** Claude (Opus) using a fixed five-topic / three-sentiment rubric, reading **review text only** (blind to the star rating).
- **Scope.** A reproducible random sample of **1,000** of the 40,977 commented reviews (`ai_sample.py`, seed 42). Labels are an LLM judgment and are stored as data in `ai/labels_bulk.csv`; they are not script-regenerable (re-running the sampler reproduces the *texts*, not the labels).
- **Validation.** A **second, independent LLM annotator (Claude)** (a separate agent in a fresh context, blind to the bulk labels) re-labeled the 200-review gold set (`ai/labels_gold_independent.csv`). Agreement between the two independent passes is inter-annotator reliability: topic **κ = 0.81** (86.5%), sentiment **κ = 0.89** (94%), both correct 82%. *Note:* a naive same-context re-label gave a non-credible 100%/κ=1.00 because it reproduced the original labels from memory — which is exactly why an independent LLM annotator was used.
- **External validity.** Text sentiment (which never saw the rating) matches the star-derived sentiment on **83%** of all 1,000; mean stars 1.8 / 3.9 / 4.8 for negative / neutral / positive.
- **Triangulation.** Delivery-topic negatives correspond to orders averaging **26 days** vs a 13-day sample baseline, linking the text to the structured r = −0.334 signal.
- **Honesty.** Both annotators are Claude (independent contexts, same model family), so the metric is reliability, not validation against human ground truth. Labels are validated on a sample, not exhaustive; full-set classification of all 40,977 is an optional API-batch extension. The product-vs-delivery boundary on missing/wrong-item orders is the main source of disagreement.

## 5. Figures

The eight figures are produced **inline in `analysis.ipynb`** from the `data/output/` aggregates and exported to `reports/charts/*.png` at 150 dpi. Each figure has an action title; the SAS interpretation lives next to the embedded image in the report.

## 6. Report generation & formatting QA

- `scripts/build_report.py` (python-docx) builds `reports/Olist_Analyst_Report.docx`: US-Letter, 1-inch margins, **Times New Roman 12pt, 1.5 spacing**, bold-only headings, embedded figures each under an action-title caption + the **Signal / Analysis / So What / Caveat** block + an analysis paragraph. A final `enforce()` pass sets the font on every run and table cell at the run level so nothing inherits a drifted font. Tables use 11pt as a deliberate, uniform exception for fit; column widths sum to the content width so no cell clips (text wraps, never truncates).
- The `.docx` passes the OOXML validator. For the manual's visual-QA gate it was rendered to PDF (via Pages) and rasterized with PyMuPDF, then reviewed page by page (no font drift, no clipped cells, SAS lines separated, figures in color).

## 7. Reproducibility & run order

`analysis.ipynb` is the entry point — it cleans at the correct grain, writes `data/output/`, and renders all eight figures inline; `build_pipeline.py` is its headless equivalent for the clean → output step. Around it: `step0_audit.py` (profiling/reconciliation) → `build_pipeline.py` (or the notebook) → `run_sql.py` (DuckDB cross-checks) → `ai_sample.py` → (LLM labels) → `ai_validate.py` → `make_docs.py` → `build_report.py`. Raw CSVs are read-only and git-ignored; everything else regenerates from them (AI labels excepted, as noted).
