# AI Review-Classification — Validation Report

## Method

- **Classifier:** Claude (Opus 4.x) using a fixed five-topic / three-sentiment rubric, reading review text only (blind to the star rating).
- **Scope:** a reproducible random sample of **1,000** of the 40,977 reviews that have `review_comment_message` (seed 42). Topics: delivery_shipping, product_quality, price_value, customer_service, other. Sentiment: negative, neutral, positive.
- **Validation set:** **200** gold reviews (seed 43) were re-labelled by a **second, independent LLM annotator (Claude)** — a separate agent run in a fresh context, blind to the bulk labels, given the same rubric and the review text only.
- **Honesty:** with no human-annotated ground truth, the gold comparison measures **inter-annotator agreement** between two independent passes, not absolute correctness. We add an **external check** of the sentiment labels against the structured star rating. Anonymized Game-of-Thrones house names in the text are not real brands.

## Headline results

- **Topic** — agreement vs gold = **86.5%** (95% CI 81.1%–90.6%); Cohen's kappa = **0.81**.
- **Sentiment** — agreement vs gold = **94.0%** (95% CI 89.8%–96.5%); Cohen's kappa = **0.89**.
- **Both correct** (topic AND sentiment) = **82.0%** of the 200 gold reviews.
- **External check** — text sentiment vs star-derived sentiment agree on **82.8%** of all 1,000 (95% CI 80.3%–85.0%).
- **Overall confidence: Medium-High for directional topic analysis.**

## Per-class agreement vs gold (recall of the independent reference label)

| Topic | gold n | recall |
|---|---:|---:|
| delivery_shipping | 74 | 77% |
| product_quality | 70 | 96% |
| price_value | 8 | 62% |
| customer_service | 11 | 82% |
| other | 37 | 95% |

| Sentiment | gold n | recall |
|---|---:|---:|
| negative | 72 | 100% |
| neutral | 21 | 52% |
| positive | 107 | 98% |

## External validity — text sentiment vs star rating

Mean star rating by predicted text sentiment (independent of the text):

| Predicted sentiment | mean stars | n |
|---|---:|---:|
| negative | 1.82 | 338 |
| neutral | 3.90 | 80 |
| positive | 4.76 | 582 |

The monotonic ordering (negative < neutral < positive) confirms the sentiment labels track the structured rating they never saw.

## Triangulation — what negative reviews are about, cross-checked vs delivery

Of 1,000 classified reviews, **338 are negative**. Their topic mix:

| Topic | negatives | % of neg | avg delivery days | avg stars |
|---|---:|---:|---:|---:|
| product_quality | 177 | 52.4% | 11.5 | 1.82 |
| delivery_shipping | 127 | 37.6% | 26.0 | 1.66 |
| customer_service | 19 | 5.6% | 15.1 | 2.00 |
| price_value | 9 | 2.7% | 13.5 | 3.78 |
| other | 6 | 1.8% | 32.9 | 1.33 |

**Product quality is the largest negative-review topic, while delivery is the most operationally measurable satisfaction risk signal.** Reviews the LLM flagged as delivery complaints took on average **26.0 days** to deliver vs **13.2 days** across the sample, and averaged **1.66 stars** vs **3.69** — aligning the review text with the structured delivery-vs-score signal, while avoiding a causal claim.

## Limitations

- Both annotators are Claude agents (independent contexts, but the same model family); agreement is inter-annotator reliability, not validation against human ground truth.
- 1,000-review sample (2.4% of reviews with text); breakdowns are directional for rare topics (price_value, customer_service have small n).
- Mixed reviews (e.g., good product / late delivery) are assigned a single dominant topic; the delivery-vs-product boundary on partial/missing-item orders is the main source of disagreement.
- Full-set classification of all 40,977 is an optional API-batch extension.
