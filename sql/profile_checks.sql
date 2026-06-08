-- profile_checks.sql — Olist data profiling + referential-integrity checks (DuckDB)
-- Run from the repo root (paths are relative). Read-only over data/raw/.
-- Each query is labelled with "-- @label:" so scripts/run_sql.py can print it.

CREATE OR REPLACE VIEW orders    AS SELECT * FROM read_csv_auto('data/raw/olist_orders_dataset.csv');
CREATE OR REPLACE VIEW items     AS SELECT * FROM read_csv_auto('data/raw/olist_order_items_dataset.csv');
CREATE OR REPLACE VIEW payments  AS SELECT * FROM read_csv_auto('data/raw/olist_order_payments_dataset.csv');
CREATE OR REPLACE VIEW reviews   AS SELECT * FROM read_csv_auto('data/raw/olist_order_reviews_dataset.csv');
CREATE OR REPLACE VIEW products  AS SELECT * FROM read_csv_auto('data/raw/olist_products_dataset.csv');
CREATE OR REPLACE VIEW customers AS SELECT * FROM read_csv_auto('data/raw/olist_customers_dataset.csv');
CREATE OR REPLACE VIEW geo       AS SELECT * FROM read_csv_auto('data/raw/olist_geolocation_dataset.csv');
CREATE OR REPLACE VIEW xlate     AS SELECT * FROM read_csv_auto('data/raw/product_category_name_translation.csv');

-- @label: 1. Row counts per table
SELECT 'orders' AS tbl, count(*) AS rows FROM orders
UNION ALL SELECT 'order_items', count(*) FROM items
UNION ALL SELECT 'order_payments', count(*) FROM payments
UNION ALL SELECT 'order_reviews', count(*) FROM reviews
UNION ALL SELECT 'products', count(*) FROM products
UNION ALL SELECT 'customers', count(*) FROM customers
UNION ALL SELECT 'geolocation', count(*) FROM geo
UNION ALL SELECT 'category_translation', count(*) FROM xlate
ORDER BY tbl;

-- @label: 2. Orders missing delivery timestamps (tied to non-delivered status)
SELECT
  count(*) FILTER (WHERE order_approved_at IS NULL)             AS missing_approved,
  count(*) FILTER (WHERE order_delivered_carrier_date IS NULL)  AS missing_carrier,
  count(*) FILTER (WHERE order_delivered_customer_date IS NULL) AS missing_delivered
FROM orders;

-- @label: 3. Review free-text coverage
SELECT
  count(*) AS reviews,
  count(*) FILTER (WHERE review_comment_message IS NULL) AS missing_message,
  count(*) FILTER (WHERE review_comment_title   IS NULL) AS missing_title,
  count(*) FILTER (WHERE review_comment_message IS NOT NULL) AS with_text,
  round(100.0 * count(*) FILTER (WHERE review_comment_message IS NOT NULL) / count(*), 2) AS pct_with_text
FROM reviews;

-- @label: 4. Products missing category
SELECT count(*) FILTER (WHERE product_category_name IS NULL) AS products_missing_category,
       count(*) AS total_products
FROM products;

-- @label: 5. Categories present in products but absent from translation
SELECT DISTINCT p.product_category_name
FROM products p
LEFT JOIN xlate x ON p.product_category_name = x.product_category_name
WHERE p.product_category_name IS NOT NULL AND x.product_category_name IS NULL
ORDER BY 1;

-- @label: 6. Geolocation duplication (rows vs unique zip prefixes)
SELECT count(*) AS geo_rows,
       count(DISTINCT geolocation_zip_code_prefix) AS unique_prefixes,
       round(count(*)::DOUBLE / count(DISTINCT geolocation_zip_code_prefix), 1) AS rows_per_prefix
FROM geo;

-- @label: 7. Fan-out: orders with multiple item rows
SELECT count(*) AS multi_item_orders, max(n) AS max_items
FROM (SELECT order_id, count(*) AS n FROM items GROUP BY order_id) t
WHERE n > 1;

-- @label: 8. Fan-out: orders with multiple payment rows
SELECT count(*) AS multi_payment_orders, max(n) AS max_payments
FROM (SELECT order_id, count(*) AS n FROM payments GROUP BY order_id) t
WHERE n > 1;

-- @label: 9. Identity collapse (customer_id vs customer_unique_id)
SELECT count(DISTINCT customer_id) AS customer_ids,
       count(DISTINCT customer_unique_id) AS unique_customers
FROM customers;

-- @label: 10. Repeat-customer rate on customer_unique_id
WITH per_customer AS (
  SELECT c.customer_unique_id, count(DISTINCT o.order_id) AS orders
  FROM orders o JOIN customers c USING (customer_id)
  GROUP BY 1)
SELECT count(*) AS customers,
       count(*) FILTER (WHERE orders > 1) AS repeat_customers,
       round(100.0 * count(*) FILTER (WHERE orders > 1) / count(*), 2) AS repeat_rate_pct
FROM per_customer;

-- @label: 11. Invalid payments (value <= 0 or undefined type)
SELECT count(*) FILTER (WHERE payment_value <= 0) AS nonpositive_value,
       count(*) FILTER (WHERE payment_type = 'not_defined') AS not_defined_type
FROM payments;

-- @label: 12. Referential integrity — item/payment/review order_ids vs orders
SELECT
  (SELECT count(*) FROM items    i LEFT JOIN orders o USING(order_id) WHERE o.order_id IS NULL) AS items_orphan_orders,
  (SELECT count(*) FROM payments p LEFT JOIN orders o USING(order_id) WHERE o.order_id IS NULL) AS payments_orphan_orders,
  (SELECT count(*) FROM reviews  r LEFT JOIN orders o USING(order_id) WHERE o.order_id IS NULL) AS reviews_orphan_orders,
  (SELECT count(*) FROM items    i LEFT JOIN products pr USING(product_id) WHERE pr.product_id IS NULL) AS items_orphan_products;

-- @label: 13. Orders with no item row and no payment row
SELECT
  (SELECT count(*) FROM orders o LEFT JOIN items i USING(order_id) WHERE i.order_id IS NULL) AS orders_without_items,
  (SELECT count(*) FROM orders o LEFT JOIN payments p USING(order_id) WHERE p.order_id IS NULL) AS orders_without_payments;

-- @label: 14. Signal: order value (items) vs payments per order, correlation
WITH oi AS (SELECT order_id, sum(price)+sum(freight_value) AS order_value FROM items GROUP BY 1),
     op AS (SELECT order_id, sum(payment_value) AS pay FROM payments GROUP BY 1)
SELECT round(corr(oi.order_value, op.pay), 4) AS r_value_vs_payment, count(*) AS n_orders
FROM oi JOIN op USING (order_id);

-- @label: 15. Order status mix
SELECT order_status, count(*) AS orders,
       round(100.0*count(*)/sum(count(*)) OVER (), 2) AS pct
FROM orders GROUP BY 1 ORDER BY orders DESC;
