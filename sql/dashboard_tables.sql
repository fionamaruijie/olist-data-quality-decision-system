-- dashboard_tables.sql — Tableau-ready aggregate definitions (DuckDB)
-- These mirror the canonical tables written by build_pipeline.py to data/output/.
-- build_pipeline.py is the single writer of data/output/*.csv; this file documents
-- the same logic in SQL and lets a reviewer reproduce the aggregates independently.
-- To materialise to disk, uncomment the COPY statements at the bottom.

CREATE OR REPLACE VIEW orders    AS SELECT * FROM read_csv_auto('data/raw/olist_orders_dataset.csv');
CREATE OR REPLACE VIEW items     AS SELECT * FROM read_csv_auto('data/raw/olist_order_items_dataset.csv');
CREATE OR REPLACE VIEW payments  AS SELECT * FROM read_csv_auto('data/raw/olist_order_payments_dataset.csv');
CREATE OR REPLACE VIEW reviews   AS SELECT * FROM read_csv_auto('data/raw/olist_order_reviews_dataset.csv');
CREATE OR REPLACE VIEW products  AS SELECT * FROM read_csv_auto('data/raw/olist_products_dataset.csv');
CREATE OR REPLACE VIEW customers AS SELECT * FROM read_csv_auto('data/raw/olist_customers_dataset.csv');
CREATE OR REPLACE VIEW xlate     AS SELECT * FROM read_csv_auto('data/raw/product_category_name_translation.csv');

CREATE OR REPLACE VIEW order_grain AS
WITH item_agg AS (
  SELECT order_id, sum(price) AS product_revenue, sum(freight_value) AS freight, count(*) AS n_items
  FROM items GROUP BY order_id)
SELECT o.order_id, o.order_status, c.customer_unique_id, c.customer_state,
       strftime(o.order_purchase_timestamp, '%Y-%m') AS purchase_ym,
       ia.product_revenue, ia.freight,
       coalesce(ia.product_revenue,0)+coalesce(ia.freight,0) AS order_value,
       (o.order_status='delivered') AS delivered,
       (epoch(o.order_delivered_customer_date)-epoch(o.order_purchase_timestamp))/86400.0 AS delivery_days,
       (o.order_delivered_customer_date > o.order_estimated_delivery_date) AS is_late
FROM orders o JOIN customers c USING (customer_id)
LEFT JOIN item_agg ia USING (order_id);

-- @label: KPI summary (decision-ready headline numbers)
WITH d AS (SELECT * FROM order_grain)
SELECT
  round((SELECT sum(price) FROM items),2)                                              AS gmv,
  round((SELECT sum(product_revenue) FROM d WHERE delivered),2)                        AS net_revenue_delivered,
  round((SELECT sum(freight_value) FROM items),2)                                      AS freight,
  (SELECT count(*) FROM orders)                                                        AS total_orders,
  (SELECT count(*) FROM d WHERE delivered)                                             AS delivered_orders,
  round(100.0*(SELECT count(*) FROM d WHERE delivered)/(SELECT count(*) FROM orders),2) AS pct_delivered,
  round((SELECT sum(product_revenue) FROM d WHERE delivered)/(SELECT count(*) FROM d WHERE delivered),2) AS aov_net,
  round((SELECT 100.0*count(*) FILTER (WHERE is_late=FALSE)/count(*) FROM d WHERE delivery_days IS NOT NULL),2) AS on_time_rate,
  round((SELECT median(delivery_days) FROM d WHERE delivery_days IS NOT NULL),2)        AS median_delivery_days,
  (SELECT count(DISTINCT customer_unique_id) FROM customers)                           AS unique_customers;

-- @label: dashboard_monthly_trend
SELECT purchase_ym,
       count(DISTINCT order_id) AS orders,
       count(DISTINCT order_id) FILTER (WHERE delivered) AS delivered_orders,
       round(sum(product_revenue),2) AS gmv
FROM order_grain WHERE product_revenue IS NOT NULL GROUP BY 1 ORDER BY 1;

-- @label: dashboard_revenue_by_state (top 8)
SELECT customer_state,
       round(sum(product_revenue),2) AS gmv,
       round(100.0*sum(product_revenue)/sum(sum(product_revenue)) OVER (),2) AS pct_gmv,
       count(DISTINCT order_id) AS orders
FROM order_grain WHERE product_revenue IS NOT NULL
GROUP BY 1 ORDER BY gmv DESC LIMIT 8;

-- @label: dashboard_score_vs_delivery
SELECT round(review_score) AS score, round(avg(delivery_days),2) AS avg_delivery_days, count(*) AS n
FROM (
  SELECT og.delivery_days, r.review_score
  FROM order_grain og
  JOIN (SELECT order_id, avg(review_score) AS review_score FROM reviews GROUP BY 1) r USING (order_id)
  WHERE og.delivery_days IS NOT NULL
) GROUP BY 1 ORDER BY 1;

-- To materialise any aggregate to a Tableau CSV, run e.g.:
-- COPY (SELECT ... ) TO 'data/output/monthly_trend.csv' (HEADER, DELIMITER ',');
