"""
make_docs.py — generate documentation/data_dictionary.csv and qa_tracker.csv
from the real schema plus the verified data-quality register. Run any time.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DOC = ROOT / "documentation"
DOC.mkdir(exist_ok=True)

if not list(RAW.glob("*.csv")):
    raise SystemExit(
        "make_docs.py needs the raw Kaggle CSVs in data/raw/ (git-ignored). Download the "
        "Olist dataset from Kaggle first. Note: the committed business-facing "
        "data_dictionary.csv / qa_tracker.csv are curated and are preserved, not regenerated.")

def write_doc(df, path):
    # The committed data_dictionary.csv / qa_tracker.csv are hand-curated, business-facing
    # versions. Never silently downgrade them to this technical baseline: if the existing file
    # has more columns than the baseline, write the baseline to a *_baseline.csv sibling instead.
    if path.exists():
        existing_cols = len(path.read_text(encoding="utf-8").splitlines()[0].split(","))
        if existing_cols > len(df.columns):
            alt = path.with_name(path.stem + "_baseline.csv")
            df.to_csv(alt, index=False)
            print(f"  [preserve] {path.name} is curated ({existing_cols} cols); "
                  f"wrote technical baseline -> {alt.name}")
            return
    df.to_csv(path, index=False)
    print(f"  [write] {path.name} ({len(df.columns)} cols, {len(df)} rows)")

DESC = {
    # orders
    "order_id": "Order identifier (spine key).",
    "customer_id": "Per-order customer key (FK to customers; NOT the person).",
    "order_status": "delivered / shipped / canceled / unavailable / invoiced / processing / created / approved.",
    "order_purchase_timestamp": "When the order was placed.",
    "order_approved_at": "Payment approval time (160 null).",
    "order_delivered_carrier_date": "Handover to carrier (1,783 null).",
    "order_delivered_customer_date": "Delivery to customer (2,965 null).",
    "order_estimated_delivery_date": "Promised delivery date.",
    # items
    "order_item_id": "Item sequence within the order (1..n).",
    "product_id": "Product key (FK to products).",
    "seller_id": "Seller key (FK to sellers).",
    "shipping_limit_date": "Seller shipping deadline.",
    "price": "Item price (BRL); summed to GMV at order grain.",
    "freight_value": "Item freight (BRL); reported separately.",
    # payments
    "payment_sequential": "Installment row sequence within the order.",
    "payment_type": "credit_card / boleto / voucher / debit_card / not_defined (3).",
    "payment_installments": "Number of installments.",
    "payment_value": "Payment amount (BRL); 9 rows <= 0.",
    # reviews
    "review_id": "Review identifier.",
    "review_score": "1–5 star rating.",
    "review_comment_title": "Optional title (87,656 null).",
    "review_comment_message": "Optional free text (58,247 null; 40,977 present).",
    "review_creation_date": "Review survey sent date.",
    "review_answer_timestamp": "Review answered date.",
    # products
    "product_category_name": "Category in Portuguese (610 null).",
    "product_name_lenght": "Title length (sic, original column name).",
    "product_description_lenght": "Description length (sic).",
    "product_photos_qty": "Number of photos.",
    "product_weight_g": "Weight (g).",
    "product_length_cm": "Length (cm).",
    "product_height_cm": "Height (cm).",
    "product_width_cm": "Width (cm).",
    # sellers / customers / geo / translation
    "seller_zip_code_prefix": "Seller zip prefix.",
    "seller_city": "Seller city.",
    "seller_state": "Seller state.",
    "customer_unique_id": "Real person key — used for RFM/repeat (99,441 ids -> 96,096).",
    "customer_zip_code_prefix": "Customer zip prefix.",
    "customer_city": "Customer city.",
    "customer_state": "Customer state (used for revenue-by-state).",
    "geolocation_zip_code_prefix": "Zip prefix (deduped to 19,015).",
    "geolocation_lat": "Latitude (mean per prefix after dedupe).",
    "geolocation_lng": "Longitude (mean per prefix after dedupe).",
    "geolocation_city": "City (modal per prefix).",
    "geolocation_state": "State (modal per prefix).",
    "product_category_name_english": "Category in English (2 added manually).",
}

DERIVED = [
    ("orders_clean", "order_product_revenue", "float", "Sum of items.price per order (GMV contribution)."),
    ("orders_clean", "order_freight", "float", "Sum of items.freight_value per order."),
    ("orders_clean", "order_value", "float", "order_product_revenue + order_freight."),
    ("orders_clean", "n_items", "int", "Item count per order (fan-out indicator; max 21)."),
    ("orders_clean", "order_payment_total", "float", "Sum of payment_value per order."),
    ("orders_clean", "n_payments", "int", "Payment-row count per order (fan-out; max 29)."),
    ("orders_clean", "n_installments", "int", "Max installments on the order."),
    ("orders_clean", "main_payment_type", "str", "Payment type of the largest payment row."),
    ("orders_clean", "delivered", "bool", "order_status == 'delivered'."),
    ("orders_clean", "delivery_days", "float", "delivered_customer - purchase, in days."),
    ("orders_clean", "est_delivery_days", "float", "estimated - purchase, in days."),
    ("orders_clean", "is_late", "bool", "delivered_customer > estimated_delivery_date."),
    ("orders_clean", "purchase_ym", "str", "Year-month of purchase."),
    ("orders_clean", "review_score", "float", "Mean review score per order."),
    ("orders_clean", "review_has_text", "int", "1 if any review has comment text."),
    ("products_clean", "category_en", "str", "English category; nulls bucketed as 'unknown'."),
    ("customer_rfm", "recency_days", "int", "Days since last purchase (ref = max purchase date)."),
    ("customer_rfm", "frequency", "int", "Distinct orders per customer_unique_id."),
    ("customer_rfm", "monetary", "float", "Total order_value per customer_unique_id."),
    ("customer_rfm", "R_score", "int", "Recency quintile (5 = most recent)."),
    ("customer_rfm", "M_score", "int", "Monetary quintile (5 = highest)."),
    ("customer_rfm", "is_repeat", "bool", "frequency >= 2 (repeat customer)."),
    ("customer_rfm", "segment", "str", "RFM segment label (transparent rule)."),
    ("review_classification", "topic", "str", "AI topic: delivery_shipping/product_quality/price_value/customer_service/other."),
    ("review_classification", "sentiment", "str", "AI sentiment: negative/neutral/positive (validated)."),
]

FILES = {
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "olist_customers_dataset.csv": "customers",
    "olist_geolocation_dataset.csv": "geolocation",
    "product_category_name_translation.csv": "category_translation",
}

rows = []
for fname, tbl in FILES.items():
    df = pd.read_csv(RAW / fname, nrows=200)
    for col in df.columns:
        rows.append([tbl, col, str(df[col].dtype), DESC.get(col, "—"), "no"])
for tbl, col, dt, desc in DERIVED:
    rows.append([tbl, col, dt, desc, "yes"])
write_doc(pd.DataFrame(rows, columns=["table", "field", "dtype", "description", "derived"]),
          DOC / "data_dictionary.csv")

qa = [
    ["DQ-01", "Join grain", "9,803 orders multi-item (max 21); 2,961 multi-payment (max 29)", "High",
     "Aggregate items & payments to order grain before joining", "Naive join inflates product revenue +4.5%, cash +26.9%", "Resolved"],
    ["DQ-02", "Geolocation", "1,000,163 rows for 19,015 zip prefixes (~53x)", "High",
     "Dedupe to one row per prefix (mean lat/lng, modal city/state)", "Prevents geo-join row explosion", "Resolved"],
    ["DQ-03", "Identity", "99,441 customer_id collapse to 96,096 customer_unique_id", "High",
     "Key RFM/repeat on customer_unique_id", "Repeat rate = 3.12% (finding, not a bug)", "Resolved"],
    ["DQ-04", "Reviews", "comment_message missing 58,247 (58.7%); title 87,656 (88.3%)", "Medium",
     "Scope text analysis to the 40,977 with text; flag, don't impute", "Voice-of-customer limited to a validated sample", "Resolved"],
    ["DQ-05", "Orders", "Missing delivery dates: delivered 2,965; carrier 1,783; approved 160", "Medium",
     "Tie to non-delivered status; exclude from delivery KPIs", "Delivery metrics computed on delivered-with-dates only", "Resolved"],
    ["DQ-06", "Products", "610 products missing category (+ name/desc/photos)", "Medium",
     "Map to English where possible; bucket nulls as 'unknown'", "Category Pareto includes an 'unknown' bucket", "Resolved"],
    ["DQ-07", "Categories", "2 PT categories absent from translation (pc_gamer, portateis_...)", "Low",
     "Add manual English labels (gaming_pc, portable_kitchen_and_food_preparers)", "74 vs 72 category total reconciled", "Resolved"],
    ["DQ-08", "Payments", "9 payments value <= 0; 3 payment_type 'not_defined'", "Low",
     "Flag and exclude from cash metrics", "Negligible effect on totals", "Resolved"],
    ["DQ-09", "Orphans", "775 orders with no item row; 1 with no payment", "Low",
     "Exclude from revenue (non-purchasable/canceled)", "Revenue computed on orders with items", "Resolved"],
    ["DQ-10", "AI derivation", "LLM review topic/sentiment labels (1,000-review sample)", "Medium",
     "Validated vs independent 2nd LLM annotator + star rating", "Topic kappa 0.81, sentiment kappa 0.89, star agree 83%", "Validated"],
    ["RI-00", "Referential integrity", "items/payments/reviews vs orders; items vs products", "Info",
     "Anti-join checks in sql/profile_checks.sql", "Zero orphans across all four checks", "Verified"],
]
write_doc(pd.DataFrame(qa, columns=["id", "area", "issue", "severity", "treatment", "impact", "status"]),
          DOC / "qa_tracker.csv")

print(f"Done. Generated technical baseline for {len(rows)} fields and {len(qa)} QA rows (curated files preserved).")
