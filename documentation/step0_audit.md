# Step 0 — Signal Check & Raw Audit

## 1. Table shapes (actual vs expected)

| Table | Rows | Cols | Expected | Match |
|---|---:|---:|---|:--:|
| olist_orders_dataset.csv | 99,441 | 8 | 99,441 x 8 | OK |
| olist_order_items_dataset.csv | 112,650 | 7 | 112,650 x 7 | OK |
| olist_order_payments_dataset.csv | 103,886 | 5 | 103,886 x 5 | OK |
| olist_order_reviews_dataset.csv | 99,224 | 7 | 99,224 x 7 | OK |
| olist_products_dataset.csv | 32,951 | 9 | 32,951 x 9 | OK |
| olist_sellers_dataset.csv | 3,095 | 4 | 3,095 x 4 | OK |
| olist_customers_dataset.csv | 99,441 | 5 | 99,441 x 5 | OK |
| olist_geolocation_dataset.csv | 1,000,163 | 5 | 1,000,163 x 5 | OK |
| product_category_name_translation.csv | 71 | 2 | 71 x 2 | OK |

## 2. Missing values per column (count, %)

- **olist_orders_dataset.csv** — order_approved_at=160 (0.2%), order_delivered_carrier_date=1,783 (1.8%), order_delivered_customer_date=2,965 (3.0%)
- **olist_order_items_dataset.csv** — no missing values
- **olist_order_payments_dataset.csv** — no missing values
- **olist_order_reviews_dataset.csv** — review_comment_title=87,656 (88.3%), review_comment_message=58,247 (58.7%)
- **olist_products_dataset.csv** — product_category_name=610 (1.9%), product_name_lenght=610 (1.9%), product_description_lenght=610 (1.9%), product_photos_qty=610 (1.9%), product_weight_g=2 (0.0%), product_length_cm=2 (0.0%), product_height_cm=2 (0.0%), product_width_cm=2 (0.0%)
- **olist_sellers_dataset.csv** — no missing values
- **olist_customers_dataset.csv** — no missing values
- **olist_geolocation_dataset.csv** — no missing values
- **product_category_name_translation.csv** — no missing values

## 3. Signal checks

- **order value vs payments**: Pearson r = **1.0000** (expected ≈ 1.000), n=98,665 orders
- **delivery days vs review score**: Pearson r = **-0.3338** (expected ≈ -0.334), n=96,359
- **median delivery_days** = **10.22** (expected ≈ 10.2)
- **mean review_score**: all reviews = **4.086**; delivered orders = **4.156** (matches the expected ≈4.16); non-delivered orders = **1.754** — undelivered orders crater satisfaction (a finding, not noise).
- **GMV** = **13,591,643.70 BRL** (13.59M, expected ≈ 13.59M)
- **freight** = **2,251,909.54 BRL** (2.25M, expected ≈ 2.25M)
- **orders** = **99,441** (expected 99,441)
- **monthly delivered orders** (by purchase month): 2016-09 → 2018-08 (23 months); peak **2017-11 = 7,289** (expected 2017-11 ≈ 7,289)

## 4. Engineering hazards (the data-quality core)

- **A. Fan-out** — 9,803 orders have >1 item (max 21); 2,961 orders have >1 payment row (max 29).
  - naive `orders x items x payments` join inflates summed price to **14.21M** vs correct GMV **13.59M** (x1.05 overcount).
- **B. Geolocation duplication** — 1,000,163 rows for only 19,015 zip prefixes (~53x).
- **C. Identity** — 99,441 customer_id collapse to 96,096 customer_unique_id; repeat-customer rate = **3.12%** (expected ≈ 3.12%).

## 5. Data-quality register (verify DQ-04 … DQ-09)

- **DQ-04 Reviews** — message missing 58,247 (58.7%); title missing 87,656 (88.3%); **40,977 have text**.
- **DQ-05 Orders** — missing delivered_customer=2,965, carrier=1,783, approved_at=160.
- **DQ-06 Products** — 610 missing category.
- **DQ-07 Categories** — 2 present in products but absent from translation: ['pc_gamer', 'portateis_cozinha_e_preparadores_de_alimentos'].
- **DQ-08 Payments** — 9 with value<=0; 3 with type `not_defined`.
- **DQ-09 Orphans** — 775 orders with no item row; 1 with no payment row.
- **Order status mix** — delivered=96,478, shipped=1,107, canceled=625, unavailable=609, invoiced=314, processing=301, created=5, approved=2

## 6. Verification verdict

**37/37 checks match the expected values.**

| Check | Expected | Actual | Match |
|---|---|---|:--:|
| shape olist_orders_dataset.csv | 99,441x8 | 99,441x8 | OK |
| shape olist_order_items_dataset.csv | 112,650x7 | 112,650x7 | OK |
| shape olist_order_payments_dataset.csv | 103,886x5 | 103,886x5 | OK |
| shape olist_order_reviews_dataset.csv | 99,224x7 | 99,224x7 | OK |
| shape olist_products_dataset.csv | 32,951x9 | 32,951x9 | OK |
| shape olist_sellers_dataset.csv | 3,095x4 | 3,095x4 | OK |
| shape olist_customers_dataset.csv | 99,441x5 | 99,441x5 | OK |
| shape olist_geolocation_dataset.csv | 1,000,163x5 | 1,000,163x5 | OK |
| shape product_category_name_translation.csv | 71x2 | 71x2 | OK |
| r(order_value, payment_value) | ≈1.000 | 1.0000 | OK |
| r(delivery_days, review_score) | ≈-0.334 | -0.3338 | OK |
| median delivery_days | ≈10.2 | 10.22 | OK |
| mean review_score (delivered) | ≈4.16 | 4.156 | OK |
| GMV (sum items.price) | ≈13.59M | 13.59M | OK |
| freight (sum freight_value) | ≈2.25M | 2.25M | OK |
| orders | 99,441 | 99,441 | OK |
| monthly span | 2016-09 → 2018-08 | 2016-09 → 2018-08 | OK |
| peak month | 2017-11 ≈ 7,289 | 2017-11 = 7,289 | OK |
| orders w/ multiple items | 9,803 (max 21) | 9,803 (max 21) | OK |
| orders w/ multiple payments | 2,961 (max 29) | 2,961 (max 29) | OK |
| geo rows | 1,000,163 | 1,000,163 | OK |
| geo unique prefixes | ≈19,015 | 19,015 | OK |
| customer_id count | 99,441 | 99,441 | OK |
| customer_unique_id count | 96,096 | 96,096 | OK |
| repeat rate | ≈3.12% | 3.12% | OK |
| reviews missing message | 58,247 (58.7%) | 58,247 (58.7%) | OK |
| reviews with text | 40,977 | 40,977 | OK |
| missing delivered_customer | 2,965 | 2,965 | OK |
| missing carrier date | 1,783 | 1,783 | OK |
| missing approved_at | 160 | 160 | OK |
| products missing category | 610 | 610 | OK |
| unmapped categories | 2 (pc_gamer, portateis…) | 2: ['pc_gamer', 'portateis_cozinha_e_preparadores_de_alimentos'] | OK |
| payments value<=0 | 9 | 9 | OK |
| payments not_defined | 3 | 3 | OK |
| orders w/o item row | 775 | 775 | OK |
| orders w/o payment row | 1 | 1 | OK |
| delivered orders | 96,478 | 96,478 | OK |