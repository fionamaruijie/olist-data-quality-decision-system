"""
build_pipeline.py — Olist raw -> cleaned -> output, reproducibly.

Reads data/raw/*.csv READ-ONLY and writes:
  data/cleaned/   order-grain and entity tables with derived fields
  data/output/    Tableau-ready aggregate tables (one row per chart/KPI need)

The three engineering hazards are handled explicitly:
  A. Fan-out      — items & payments aggregated to ORDER grain before joining.
  B. Geo dup      — geolocation deduped to one row per zip prefix.
  C. Identity     — RFM / repeat keyed on customer_unique_id, not customer_id.

Run:  .venv/bin/python build_pipeline.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "cleaned"
OUT = ROOT / "data" / "output"
CLEAN.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

BRL = 2  # round money to 2 dp

# Manual EN labels for the 2 categories missing from the translation table (DQ-07)
MANUAL_CATEGORY_EN = {
    "pc_gamer": "gaming_pc",
    "portateis_cozinha_e_preparadores_de_alimentos": "portable_kitchen_and_food_preparers",
}

def load(name):
    return pd.read_csv(RAW / name)

print("Loading raw tables (read-only) ...")
orders    = load("olist_orders_dataset.csv")
items     = load("olist_order_items_dataset.csv")
payments  = load("olist_order_payments_dataset.csv")
reviews   = load("olist_order_reviews_dataset.csv")
products  = load("olist_products_dataset.csv")
sellers   = load("olist_sellers_dataset.csv")
customers = load("olist_customers_dataset.csv")
geo       = load("olist_geolocation_dataset.csv")
cat_xlate = load("product_category_name_translation.csv")

for c in ["order_purchase_timestamp", "order_approved_at",
          "order_delivered_carrier_date", "order_delivered_customer_date",
          "order_estimated_delivery_date"]:
    orders[c] = pd.to_datetime(orders[c], errors="coerce")

# ===========================================================================
# Hazard B — deduplicate geolocation to one row per zip prefix
# ===========================================================================
def fast_mode(df, key, col):
    """Most frequent `col` per `key`, vectorized."""
    g = df.groupby([key, col]).size().reset_index(name="n")
    g = g.sort_values("n").drop_duplicates(key, keep="last")
    return g.set_index(key)[col]

print("Hazard B: deduplicating geolocation ...")
geo_clean = geo.groupby("geolocation_zip_code_prefix").agg(
    lat=("geolocation_lat", "mean"),
    lng=("geolocation_lng", "mean"),
).join(fast_mode(geo, "geolocation_zip_code_prefix", "geolocation_city").rename("city"))
geo_clean = geo_clean.join(
    fast_mode(geo, "geolocation_zip_code_prefix", "geolocation_state").rename("state"))
geo_clean = geo_clean.reset_index().rename(columns={"geolocation_zip_code_prefix": "zip_prefix"})
print(f"   {len(geo):,} geo rows -> {len(geo_clean):,} unique prefixes")

# ===========================================================================
# Products — English category, unknown bucket, manual labels (DQ-06/07)
# ===========================================================================
print("Products: mapping categories to English ...")
products_clean = products.merge(cat_xlate, on="product_category_name", how="left")
# manual labels for the 2 untranslated categories
mask_manual = products_clean["product_category_name"].isin(MANUAL_CATEGORY_EN)
products_clean.loc[mask_manual, "product_category_name_english"] = (
    products_clean.loc[mask_manual, "product_category_name"].map(MANUAL_CATEGORY_EN))
# 610 missing category -> 'unknown'
products_clean["category_en"] = products_clean["product_category_name_english"].fillna("unknown")
products_clean = products_clean[["product_id", "product_category_name", "category_en"]]

# ===========================================================================
# Hazard A — aggregate items & payments to ORDER grain (no fan-out)
# ===========================================================================
print("Hazard A: aggregating items & payments to order grain ...")
item_agg = items.groupby("order_id").agg(
    order_product_revenue=("price", "sum"),
    order_freight=("freight_value", "sum"),
    n_items=("order_item_id", "count"),
    n_sellers=("seller_id", "nunique"),
)

pay_agg = payments.groupby("order_id").agg(
    order_payment_total=("payment_value", "sum"),
    n_payments=("payment_value", "size"),
    n_installments=("payment_installments", "max"),
)
# main payment type = type of the largest single payment row in the order
main_type = (payments.sort_values("payment_value")
             .drop_duplicates("order_id", keep="last")
             .set_index("order_id")["payment_type"].rename("main_payment_type"))

rev_flag = reviews.assign(has_text=reviews["review_comment_message"].notna())
rev_agg = rev_flag.groupby("order_id").agg(
    review_score=("review_score", "mean"),
    n_reviews=("review_id", "size"),
    review_has_text=("has_text", "max"),
)

# ===========================================================================
# Order-grain clean table + derived fields
# ===========================================================================
print("Assembling order-grain clean table ...")
oc = orders.merge(
    customers[["customer_id", "customer_unique_id",
               "customer_zip_code_prefix", "customer_city", "customer_state"]],
    on="customer_id", how="left")
oc = (oc.join(item_agg, on="order_id")
        .join(pay_agg, on="order_id")
        .join(main_type, on="order_id")
        .join(rev_agg, on="order_id"))

oc["has_items"] = oc["order_product_revenue"].notna()
oc["has_payment"] = oc["order_payment_total"].notna()
for c in ["order_product_revenue", "order_freight", "n_items", "n_sellers"]:
    oc[c] = oc[c].fillna(0)
oc["order_value"] = oc["order_product_revenue"] + oc["order_freight"]

oc["delivered"] = oc["order_status"].eq("delivered")
oc["delivery_days"] = (oc["order_delivered_customer_date"]
                       - oc["order_purchase_timestamp"]).dt.total_seconds() / 86400.0
oc["est_delivery_days"] = (oc["order_estimated_delivery_date"]
                           - oc["order_purchase_timestamp"]).dt.total_seconds() / 86400.0
# is_late only where actually delivered
delivered_known = oc["order_delivered_customer_date"].notna()
oc["is_late"] = np.where(
    delivered_known,
    oc["order_delivered_customer_date"] > oc["order_estimated_delivery_date"],
    np.nan)
oc["purchase_ym"] = oc["order_purchase_timestamp"].dt.to_period("M").astype(str)
oc["purchase_date"] = oc["order_purchase_timestamp"].dt.date
oc["review_has_text"] = oc["review_has_text"].fillna(0).astype(int)

# ===========================================================================
# Hazard C — RFM on customer_unique_id
# ===========================================================================
print("Hazard C: RFM on customer_unique_id ...")
ref_date = oc["order_purchase_timestamp"].max()
rfm = oc.groupby("customer_unique_id").agg(
    recency_days=("order_purchase_timestamp", lambda s: (ref_date - s.max()).days),
    frequency=("order_id", "nunique"),
    monetary=("order_value", "sum"),
).reset_index()
# transparent scoring: recency & monetary quintiles (rank to break ties)
rfm["R_score"] = pd.qcut(rfm["recency_days"].rank(method="first"), 5,
                         labels=[5, 4, 3, 2, 1]).astype(int)   # recent = 5
rfm["M_score"] = pd.qcut(rfm["monetary"].rank(method="first"), 5,
                         labels=[1, 2, 3, 4, 5]).astype(int)    # high = 5
rfm["is_repeat"] = (rfm["frequency"] >= 2)

def segment(r):
    if r.frequency >= 2:
        return "Repeat (Loyal/Champion)"
    if r.R_score >= 4 and r.M_score >= 4:
        return "New high-value"
    if r.R_score >= 4:
        return "New / recent"
    if r.R_score <= 2 and r.M_score >= 4:
        return "Dormant high-value"
    if r.R_score <= 2:
        return "Dormant"
    return "Mid one-time"

rfm["segment"] = rfm.apply(segment, axis=1)

# ===========================================================================
# Write cleaned tables
# ===========================================================================
print("Writing data/cleaned/ ...")
oc.to_csv(CLEAN / "orders_clean.csv", index=False)
geo_clean.to_csv(CLEAN / "geo_clean.csv", index=False)
products_clean.to_csv(CLEAN / "products_clean.csv", index=False)
rfm.to_csv(CLEAN / "customer_rfm.csv", index=False)
# item-grain with English category (for category analysis)
items_clean = items.merge(products_clean[["product_id", "category_en"]],
                          on="product_id", how="left")
items_clean["category_en"] = items_clean["category_en"].fillna("unknown")
items_clean.to_csv(CLEAN / "order_items_clean.csv", index=False)

# ===========================================================================
# OUTPUT TABLES (Tableau-ready aggregates)
# ===========================================================================
print("Writing data/output/ aggregates ...")
with_items = oc[oc["has_items"]].copy()
delivered = oc[oc["delivered"]].copy()

# --- KPI summary -----------------------------------------------------------
gmv = with_items["order_product_revenue"].sum()
net_rev = delivered["order_product_revenue"].sum()
freight = with_items["order_freight"].sum()
n_orders = oc["order_id"].nunique()
n_delivered = int(oc["delivered"].sum())
aov_net = net_rev / n_delivered
deliv_known = oc[oc["order_delivered_customer_date"].notna()]
on_time_rate = (~deliv_known["is_late"].astype(bool)).mean() * 100
med_delivery = deliv_known["delivery_days"].median()
p90_delivery = deliv_known["delivery_days"].quantile(0.90)
repeat_rate = rfm["is_repeat"].mean() * 100
n_customers = rfm.shape[0]
pct_reviews_text = reviews["review_comment_message"].notna().mean() * 100

kpi = pd.DataFrame([
    ("GMV (product revenue, BRL)", round(gmv, BRL)),
    ("Net product revenue, delivered (BRL)", round(net_rev, BRL)),
    ("Freight (BRL)", round(freight, BRL)),
    ("Total orders", n_orders),
    ("Delivered orders", n_delivered),
    ("% delivered", round(n_delivered / n_orders * 100, 2)),
    ("AOV net (BRL/delivered order)", round(aov_net, BRL)),
    ("On-time delivery rate (%)", round(on_time_rate, 2)),
    ("Median delivery days", round(med_delivery, 2)),
    ("P90 delivery days", round(p90_delivery, 2)),
    ("Unique customers (customer_unique_id)", n_customers),
    ("Repeat-customer rate (%)", round(repeat_rate, 2)),
    ("% reviews with text", round(pct_reviews_text, 2)),
], columns=["kpi", "value"])
kpi.to_csv(OUT / "kpi_summary.csv", index=False)

# --- 1. monthly trend ------------------------------------------------------
monthly = (with_items.groupby("purchase_ym")
           .agg(orders=("order_id", "nunique"),
                gmv=("order_product_revenue", "sum")).reset_index())
deliv_month = (delivered.groupby("purchase_ym")
               .agg(delivered_orders=("order_id", "nunique")).reset_index())
monthly = monthly.merge(deliv_month, on="purchase_ym", how="left")
monthly["gmv"] = monthly["gmv"].round(BRL)
monthly.to_csv(OUT / "monthly_trend.csv", index=False)

# --- 2. category revenue Pareto -------------------------------------------
cat_rev = (items_clean.groupby("category_en")["price"].sum()
           .sort_values(ascending=False).reset_index()
           .rename(columns={"price": "revenue"}))
cat_rev["revenue"] = cat_rev["revenue"].round(BRL)
cat_rev["pct"] = cat_rev["revenue"] / cat_rev["revenue"].sum() * 100
cat_rev["cum_pct"] = cat_rev["pct"].cumsum()
cat_rev["rank"] = np.arange(1, len(cat_rev) + 1)
cat_rev.to_csv(OUT / "category_revenue_pareto.csv", index=False)

# --- 3. delivery-time distribution ----------------------------------------
bins = [0, 5, 10, 15, 20, 25, 30, 40, 60, np.inf]
labels = ["0-5", "5-10", "10-15", "15-20", "20-25", "25-30", "30-40", "40-60", "60+"]
dd = deliv_known.copy()
dd["bucket"] = pd.cut(dd["delivery_days"], bins=bins, labels=labels, right=False)
delivery_dist = (dd.groupby("bucket", observed=False)
                 .agg(orders=("order_id", "nunique")).reset_index())
delivery_dist["pct"] = delivery_dist["orders"] / delivery_dist["orders"].sum() * 100
delivery_dist.to_csv(OUT / "delivery_distribution.csv", index=False)

# --- 4. review score vs delivery delay ------------------------------------
score_delay = (deliv_known.dropna(subset=["review_score"])
               .assign(score=lambda d: d["review_score"].round().astype(int))
               .groupby("score")
               .agg(mean_delivery_days=("delivery_days", "mean"),
                    median_delivery_days=("delivery_days", "median"),
                    late_rate=("is_late", lambda s: s.astype(float).mean() * 100),
                    n=("order_id", "nunique")).reset_index())
score_delay["mean_delivery_days"] = score_delay["mean_delivery_days"].round(2)
score_delay["median_delivery_days"] = score_delay["median_delivery_days"].round(2)
score_delay["late_rate"] = score_delay["late_rate"].round(2)
# pearson r for the report
r_score = deliv_known.dropna(subset=["review_score"])["delivery_days"].corr(
    deliv_known.dropna(subset=["review_score"])["review_score"])
score_delay.to_csv(OUT / "score_vs_delivery.csv", index=False)

# --- 5. RFM segments + repeat summary -------------------------------------
seg = (rfm.groupby("segment")
       .agg(customers=("customer_unique_id", "nunique"),
            avg_monetary=("monetary", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_recency=("recency_days", "mean")).reset_index()
       .sort_values("customers", ascending=False))
seg["pct_customers"] = (seg["customers"] / seg["customers"].sum() * 100).round(2)
seg["avg_monetary"] = seg["avg_monetary"].round(2)
seg["avg_frequency"] = seg["avg_frequency"].round(3)
seg["avg_recency"] = seg["avg_recency"].round(1)
seg.to_csv(OUT / "rfm_segments.csv", index=False)

freq_bucket = rfm["frequency"].apply(lambda f: "1" if f == 1 else ("2" if f == 2 else "3+"))
repeat = (rfm.assign(freq_bucket=freq_bucket).groupby("freq_bucket")
          .agg(customers=("customer_unique_id", "nunique"),
               revenue=("monetary", "sum")).reset_index())
repeat["pct_customers"] = (repeat["customers"] / repeat["customers"].sum() * 100).round(2)
repeat["pct_revenue"] = (repeat["revenue"] / repeat["revenue"].sum() * 100).round(2)
repeat["revenue"] = repeat["revenue"].round(2)
repeat.to_csv(OUT / "repeat_summary.csv", index=False)

# --- 6. revenue by state ---------------------------------------------------
state_rev = (with_items.groupby("customer_state")
             .agg(gmv=("order_product_revenue", "sum"),
                  orders=("order_id", "nunique"),
                  customers=("customer_unique_id", "nunique")).reset_index()
             .sort_values("gmv", ascending=False))
state_rev["gmv"] = state_rev["gmv"].round(2)
state_rev["pct_gmv"] = (state_rev["gmv"] / state_rev["gmv"].sum() * 100).round(2)
state_rev.to_csv(OUT / "revenue_by_state.csv", index=False)

# --- 7. raw-vs-decision-ready reconciliation ------------------------------
naive = orders.merge(items, on="order_id", how="inner").merge(payments, on="order_id", how="inner")
naive_rows = len(naive)
naive_price = naive["price"].sum()
naive_pay = naive["payment_value"].sum()
naive_distinct_orders = naive["order_id"].nunique()
naive_aov = naive_price / naive_distinct_orders
correct_pay = payments["payment_value"].sum()
correct_aov = gmv / with_items["order_id"].nunique()
recon = pd.DataFrame([
    ("Join rows used for revenue", naive_rows, with_items.shape[0],
     "orders x items x payments explodes; correct view is one row per order"),
    ("Product revenue (sum price, BRL)", round(naive_price, 2), round(gmv, 2),
     "price repeated once per payment row in the naive join"),
    ("Cash collected (sum payment_value, BRL)", round(naive_pay, 2), round(correct_pay, 2),
     "payment_value repeated once per item row in the naive join"),
    ("AOV (BRL per order)", round(naive_aov, 2), round(correct_aov, 2),
     "naive AOV inflated by the same double-count"),
], columns=["metric", "naive_raw", "decision_ready", "why"])
recon["inflation_pct"] = ((recon["naive_raw"] - recon["decision_ready"])
                          / recon["decision_ready"] * 100).round(2)
recon.to_csv(OUT / "reconciliation.csv", index=False)

# ===========================================================================
# Summary
# ===========================================================================
print("\n" + "=" * 64)
print("PIPELINE COMPLETE — headline KPIs (decision-ready):")
for _, row in kpi.iterrows():
    v = f"{row['value']:,.2f}" if isinstance(row['value'], float) else f"{row['value']:,}"
    print(f"  {row['kpi']:<42} {v}")
print("-" * 64)
print(f"  r(delivery_days, review_score) on delivered : {r_score:.4f}")
print(f"  Categories for 80% of revenue               : "
      f"{int((cat_rev['cum_pct'] <= 80).sum()) + 1} of {len(cat_rev)}")
print(f"  Top state (GMV)                             : "
      f"{state_rev.iloc[0]['customer_state']} = {state_rev.iloc[0]['pct_gmv']:.1f}%")
print(f"  Naive revenue overcount                     : "
      f"{naive_price/gmv:.3f}x ({naive_price/1e6:.2f}M vs {gmv/1e6:.2f}M)")
print("=" * 64)
written = sorted([p.name for p in OUT.glob("*.csv")])
print(f"data/output/: {', '.join(written)}")
print(f"data/cleaned/: {', '.join(sorted(p.name for p in CLEAN.glob('*.csv')))}")
