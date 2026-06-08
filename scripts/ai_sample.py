"""
ai_sample.py — draw the reproducible review sample for in-session LLM classification.

Scope: the 40,977 reviews with review_comment_message (Portuguese).
- analysis sample: 1,000 random reviews (seed 42)
- gold subset:     200 of those (seed 43), re-labelled independently for validation

Writes:
  ai/sample_for_labeling.csv  idx, review_id, order_id, review_score, delivery_days, in_gold, text
  ai/_to_label.txt            "idx<TAB>text" per line (clean reading copy for labelling)
Nothing in data/raw/ is modified.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "cleaned"
AI = ROOT / "ai"
AI.mkdir(exist_ok=True)

N_SAMPLE, N_GOLD = 1000, 200

reviews = pd.read_csv(RAW / "olist_order_reviews_dataset.csv")
oc = pd.read_csv(CLEAN / "orders_clean.csv", usecols=["order_id", "delivery_days", "order_status"])

df = reviews[reviews["review_comment_message"].notna()].copy()
df = df.merge(oc, on="order_id", how="left")

samp = df.sample(N_SAMPLE, random_state=42).reset_index(drop=True)
samp.insert(0, "idx", range(len(samp)))
gold_idx = set(samp.sample(N_GOLD, random_state=43)["idx"].tolist())
samp["in_gold"] = samp["idx"].isin(gold_idx).astype(int)
samp["text"] = (samp["review_comment_message"].astype(str)
                .str.replace(r"\s+", " ", regex=True).str.strip())

cols = ["idx", "review_id", "order_id", "review_score", "delivery_days", "in_gold", "text"]
samp[cols].to_csv(AI / "sample_for_labeling.csv", index=False)

with open(AI / "_to_label.txt", "w", encoding="utf-8") as f:
    for _, r in samp.iterrows():
        f.write(f"{r['idx']}\t{r['text']}\n")

print(f"Sampled {len(samp)} reviews; {samp['in_gold'].sum()} gold.")
print("review_score distribution:",
      samp["review_score"].value_counts().sort_index().to_dict())
print("median delivery_days in sample:", round(samp["delivery_days"].median(), 2))
print("gold idx (sorted, first 30):", sorted(gold_idx)[:30], "...")
