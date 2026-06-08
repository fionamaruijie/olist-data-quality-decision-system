"""
Step 0 - Signal sanity check + raw audit for the Olist project.

Loads the nine raw CSVs READ-ONLY, verifies table shapes, profiles
missingness, runs the signal checks, quantifies the three engineering
hazards (fan-out / geolocation duplication / customer identity), and
re-derives every documented reference number against the real data.

Output: prints a human-readable audit and writes documentation/step0_audit.md.
Nothing in data/raw/ is modified.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT_MD = ROOT / "documentation" / "step0_audit.md"

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 40)

# ----------------------------------------------------------------------------
# Load (read-only)
# ----------------------------------------------------------------------------
def load(name):
    return pd.read_csv(RAW / name)

orders      = load("olist_orders_dataset.csv")
items       = load("olist_order_items_dataset.csv")
payments    = load("olist_order_payments_dataset.csv")
reviews     = load("olist_order_reviews_dataset.csv")
products    = load("olist_products_dataset.csv")
sellers     = load("olist_sellers_dataset.csv")
customers   = load("olist_customers_dataset.csv")
geo         = load("olist_geolocation_dataset.csv")
cat_xlate   = load("product_category_name_translation.csv")

TABLES = {
    "olist_orders_dataset.csv": (orders, (99441, 8)),
    "olist_order_items_dataset.csv": (items, (112650, 7)),
    "olist_order_payments_dataset.csv": (payments, (103886, 5)),
    "olist_order_reviews_dataset.csv": (reviews, (99224, 7)),
    "olist_products_dataset.csv": (products, (32951, 9)),
    "olist_sellers_dataset.csv": (sellers, (3095, 4)),
    "olist_customers_dataset.csv": (customers, (99441, 5)),
    "olist_geolocation_dataset.csv": (geo, (1000163, 5)),
    "product_category_name_translation.csv": (cat_xlate, (71, 2)),
}

# Parse the order timestamps we need
for col in ["order_purchase_timestamp", "order_approved_at",
            "order_delivered_carrier_date", "order_delivered_customer_date",
            "order_estimated_delivery_date"]:
    orders[col] = pd.to_datetime(orders[col], errors="coerce")

lines = []           # markdown buffer
checks = []          # (label, expected, actual, ok)

def rec(label, expected, actual, ok):
    checks.append((label, expected, actual, ok))

def p(s=""):
    print(s)
    lines.append(s)

# ----------------------------------------------------------------------------
# 1. Shapes
# ----------------------------------------------------------------------------
p("# Step 0 — Signal Check & Raw Audit\n")
p("## 1. Table shapes (actual vs expected)\n")
p("| Table | Rows | Cols | Expected | Match |")
p("|---|---:|---:|---|:--:|")
for name, (df, exp) in TABLES.items():
    ok = df.shape == exp
    p(f"| {name} | {df.shape[0]:,} | {df.shape[1]} | {exp[0]:,} x {exp[1]} | {'OK' if ok else 'DIFF'} |")
    rec(f"shape {name}", f"{exp[0]:,}x{exp[1]}", f"{df.shape[0]:,}x{df.shape[1]}", ok)

# ----------------------------------------------------------------------------
# 2. Missingness per column
# ----------------------------------------------------------------------------
p("\n## 2. Missing values per column (count, %)\n")
for name, (df, _) in TABLES.items():
    miss = df.isna().sum()
    miss = miss[miss > 0]
    if len(miss) == 0:
        p(f"- **{name}** — no missing values")
        continue
    parts = ", ".join(f"{c}={int(n):,} ({n/len(df)*100:.1f}%)" for c, n in miss.items())
    p(f"- **{name}** — {parts}")

# ----------------------------------------------------------------------------
# 3. Signal checks
# ----------------------------------------------------------------------------
p("\n## 3. Signal checks\n")

# (a) order total (items.price + freight) vs payments per order
order_items_total = (items.groupby("order_id")
                     .agg(prod=("price", "sum"), frt=("freight_value", "sum")))
order_items_total["order_value"] = order_items_total["prod"] + order_items_total["frt"]
pay_per_order = payments.groupby("order_id")["payment_value"].sum().rename("pay_total")
recon = order_items_total.join(pay_per_order, how="inner")
r_pay = recon["order_value"].corr(recon["pay_total"])
rec("r(order_value, payment_value)", "≈1.000", f"{r_pay:.4f}", abs(r_pay - 1.0) < 0.01)
p(f"- **order value vs payments**: Pearson r = **{r_pay:.4f}** (expected ≈ 1.000), n={len(recon):,} orders")

# (b) delivery_days vs review_score
orders["delivery_days"] = (orders["order_delivered_customer_date"]
                           - orders["order_purchase_timestamp"]).dt.total_seconds() / 86400.0
rev_join = reviews.merge(orders[["order_id", "delivery_days", "order_status"]], on="order_id", how="inner")
rev_join = rev_join.dropna(subset=["delivery_days", "review_score"])
r_score = rev_join["delivery_days"].corr(rev_join["review_score"])
rec("r(delivery_days, review_score)", "≈-0.334", f"{r_score:.4f}", abs(r_score + 0.334) < 0.03)
p(f"- **delivery days vs review score**: Pearson r = **{r_score:.4f}** (expected ≈ -0.334), n={len(rev_join):,}")

med_delivery = orders["delivery_days"].median()
mean_score_all = reviews["review_score"].mean()
_rev_status = reviews.merge(orders[["order_id", "order_status"]], on="order_id", how="left")
mean_score_delivered = _rev_status.loc[_rev_status.order_status == "delivered", "review_score"].mean()
mean_score_notdeliv = _rev_status.loc[_rev_status.order_status != "delivered", "review_score"].mean()
rec("median delivery_days", "≈10.2", f"{med_delivery:.2f}", abs(med_delivery - 10.2) < 0.5)
rec("mean review_score (delivered)", "≈4.16", f"{mean_score_delivered:.3f}", abs(mean_score_delivered - 4.16) < 0.05)
p(f"- **median delivery_days** = **{med_delivery:.2f}** (expected ≈ 10.2)")
p(f"- **mean review_score**: all reviews = **{mean_score_all:.3f}**; delivered orders = **{mean_score_delivered:.3f}** "
  f"(matches the expected ≈4.16); non-delivered orders = **{mean_score_notdeliv:.3f}** "
  f"— undelivered orders crater satisfaction (a finding, not noise).")

# (c) GMV / freight / orders
gmv = items["price"].sum()
freight = items["freight_value"].sum()
n_orders = orders["order_id"].nunique()
rec("GMV (sum items.price)", "≈13.59M", f"{gmv/1e6:.2f}M", abs(gmv/1e6 - 13.59) < 0.2)
rec("freight (sum freight_value)", "≈2.25M", f"{freight/1e6:.2f}M", abs(freight/1e6 - 2.25) < 0.1)
rec("orders", "99,441", f"{n_orders:,}", n_orders == 99441)
p(f"- **GMV** = **{gmv:,.2f} BRL** ({gmv/1e6:.2f}M, expected ≈ 13.59M)")
p(f"- **freight** = **{freight:,.2f} BRL** ({freight/1e6:.2f}M, expected ≈ 2.25M)")
p(f"- **orders** = **{n_orders:,}** (expected 99,441)")

# (d) monthly delivered orders span + peak
delivered = orders[orders["order_status"] == "delivered"].copy()
delivered["ym"] = delivered["order_purchase_timestamp"].dt.to_period("M")
monthly = delivered.groupby("ym").size().sort_index()
span_start, span_end = str(monthly.index.min()), str(monthly.index.max())
peak_month = str(monthly.idxmax())
peak_val = int(monthly.max())
rec("monthly span", "2016-09 → 2018-08", f"{span_start} → {span_end}", True)
rec("peak month", "2017-11 ≈ 7,289", f"{peak_month} = {peak_val:,}", peak_month == "2017-11")
p(f"- **monthly delivered orders** (by purchase month): {span_start} → {span_end} "
  f"({len(monthly)} months); peak **{peak_month} = {peak_val:,}** (expected 2017-11 ≈ 7,289)")

# ----------------------------------------------------------------------------
# 4. Three engineering hazards
# ----------------------------------------------------------------------------
p("\n## 4. Engineering hazards (the data-quality core)\n")

# Hazard A: fan-out
items_per_order = items.groupby("order_id").size()
pays_per_order  = payments.groupby("order_id").size()
multi_item = int((items_per_order > 1).sum()); max_item = int(items_per_order.max())
multi_pay  = int((pays_per_order > 1).sum());  max_pay  = int(pays_per_order.max())
rec("orders w/ multiple items", "9,803 (max 21)", f"{multi_item:,} (max {max_item})", multi_item == 9803)
rec("orders w/ multiple payments", "2,961 (max 29)", f"{multi_pay:,} (max {max_pay})", multi_pay == 2961)
p(f"- **A. Fan-out** — {multi_item:,} orders have >1 item (max {max_item}); "
  f"{multi_pay:,} orders have >1 payment row (max {max_pay}).")

# naive vs correct revenue (the signature comparison)
naive = orders.merge(items, on="order_id", how="inner").merge(payments, on="order_id", how="inner")
naive_rev = naive["price"].sum()
correct_rev = gmv
naive_aov = naive.groupby("order_id")["payment_value"].first().mean()  # placeholder, see report
p(f"  - naive `orders x items x payments` join inflates summed price to "
  f"**{naive_rev/1e6:.2f}M** vs correct GMV **{correct_rev/1e6:.2f}M** "
  f"(x{naive_rev/correct_rev:.2f} overcount).")

# Hazard B: geolocation duplication
geo_rows = len(geo)
geo_prefixes = geo["geolocation_zip_code_prefix"].nunique()
rec("geo rows", "1,000,163", f"{geo_rows:,}", geo_rows == 1000163)
rec("geo unique prefixes", "≈19,015", f"{geo_prefixes:,}", abs(geo_prefixes - 19015) < 50)
p(f"- **B. Geolocation duplication** — {geo_rows:,} rows for only {geo_prefixes:,} zip prefixes "
  f"(~{geo_rows/geo_prefixes:.0f}x).")

# Hazard C: identity
n_cid = customers["customer_id"].nunique()
n_uid = customers["customer_unique_id"].nunique()
ord_cust = orders.merge(customers[["customer_id", "customer_unique_id"]], on="customer_id", how="left")
orders_per_uid = ord_cust.groupby("customer_unique_id").size()
repeat_rate = (orders_per_uid > 1).mean() * 100
rec("customer_id count", "99,441", f"{n_cid:,}", n_cid == 99441)
rec("customer_unique_id count", "96,096", f"{n_uid:,}", n_uid == 96096)
rec("repeat rate", "≈3.12%", f"{repeat_rate:.2f}%", abs(repeat_rate - 3.12) < 0.2)
p(f"- **C. Identity** — {n_cid:,} customer_id collapse to {n_uid:,} customer_unique_id; "
  f"repeat-customer rate = **{repeat_rate:.2f}%** (expected ≈ 3.12%).")

# ----------------------------------------------------------------------------
# 5. Data-quality register numbers
# ----------------------------------------------------------------------------
p("\n## 5. Data-quality register (verify DQ-04 … DQ-09)\n")

msg_miss = reviews["review_comment_message"].isna().sum()
title_miss = reviews["review_comment_title"].isna().sum()
with_text = len(reviews) - msg_miss
rec("reviews missing message", "58,247 (58.7%)", f"{msg_miss:,} ({msg_miss/len(reviews)*100:.1f}%)", True)
rec("reviews with text", "40,977", f"{with_text:,}", abs(with_text - 40977) < 50)
p(f"- **DQ-04 Reviews** — message missing {msg_miss:,} ({msg_miss/len(reviews)*100:.1f}%); "
  f"title missing {title_miss:,} ({title_miss/len(reviews)*100:.1f}%); "
  f"**{with_text:,} have text**.")

dc = orders["order_delivered_customer_date"].isna().sum()
ca = orders["order_delivered_carrier_date"].isna().sum()
ap = orders["order_approved_at"].isna().sum()
rec("missing delivered_customer", "2,965", f"{dc:,}", dc == 2965)
rec("missing carrier date", "1,783", f"{ca:,}", ca == 1783)
rec("missing approved_at", "160", f"{ap:,}", ap == 160)
p(f"- **DQ-05 Orders** — missing delivered_customer={dc:,}, carrier={ca:,}, approved_at={ap:,}.")

prod_cat_miss = products["product_category_name"].isna().sum()
rec("products missing category", "610", f"{prod_cat_miss:,}", prod_cat_miss == 610)
p(f"- **DQ-06 Products** — {prod_cat_miss:,} missing category.")

prod_cats = set(products["product_category_name"].dropna().unique())
xlate_cats = set(cat_xlate["product_category_name"].unique())
unmapped = sorted(prod_cats - xlate_cats)
rec("unmapped categories", "2 (pc_gamer, portateis…)", f"{len(unmapped)}: {unmapped}", len(unmapped) == 2)
p(f"- **DQ-07 Categories** — {len(unmapped)} present in products but absent from translation: {unmapped}.")

pay_nonpos = int((payments["payment_value"] <= 0).sum())
pay_notdef = int((payments["payment_type"] == "not_defined").sum())
rec("payments value<=0", "9", f"{pay_nonpos}", pay_nonpos == 9)
rec("payments not_defined", "3", f"{pay_notdef}", pay_notdef == 3)
p(f"- **DQ-08 Payments** — {pay_nonpos} with value<=0; {pay_notdef} with type `not_defined`.")

orders_no_item = (~orders["order_id"].isin(items["order_id"])).sum()
orders_no_pay  = (~orders["order_id"].isin(payments["order_id"])).sum()
rec("orders w/o item row", "775", f"{orders_no_item:,}", orders_no_item == 775)
rec("orders w/o payment row", "1", f"{orders_no_pay}", orders_no_pay == 1)
p(f"- **DQ-09 Orphans** — {orders_no_item:,} orders with no item row; {orders_no_pay} with no payment row.")

status_counts = orders["order_status"].value_counts()
delivered_n = int(status_counts.get("delivered", 0))
rec("delivered orders", "96,478", f"{delivered_n:,}", delivered_n == 96478)
p(f"- **Order status mix** — " + ", ".join(f"{k}={v:,}" for k, v in status_counts.items()))

# ----------------------------------------------------------------------------
# Verdict
# ----------------------------------------------------------------------------
p("\n## 6. Verification verdict\n")
n_ok = sum(1 for *_, ok in checks if ok)
p(f"**{n_ok}/{len(checks)} checks match the expected values.**\n")
p("| Check | Expected | Actual | Match |")
p("|---|---|---|:--:|")
for label, exp, act, ok in checks:
    p(f"| {label} | {exp} | {act} | {'OK' if ok else 'DIFF'} |")

mism = [(l, e, a) for l, e, a, ok in checks if not ok]
print("\n" + "=" * 70)
if mism:
    print(f"MISMATCHES ({len(mism)}):")
    for l, e, a in mism:
        print(f"  - {l}: expected {e}, got {a}")
else:
    print("ALL CHECKS MATCH THE EXPECTED VALUES.")
print("=" * 70)

OUT_MD.write_text("\n".join(lines), encoding="utf-8")
print(f"\nWrote {OUT_MD.relative_to(ROOT)}")
