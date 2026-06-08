-- business_questions.sql — the decision questions, answered in SQL (DuckDB)
-- Run from the repo root. Uses raw CSVs; aggregates items/payments to ORDER grain
-- first so revenue is never double-counted by the fan-out.

CREATE OR REPLACE VIEW orders    AS SELECT * FROM read_csv_auto('data/raw/olist_orders_dataset.csv');
CREATE OR REPLACE VIEW items     AS SELECT * FROM read_csv_auto('data/raw/olist_order_items_dataset.csv');
CREATE OR REPLACE VIEW payments  AS SELECT * FROM read_csv_auto('data/raw/olist_order_payments_dataset.csv');
CREATE OR REPLACE VIEW reviews   AS SELECT * FROM read_csv_auto('data/raw/olist_order_reviews_dataset.csv');
CREATE OR REPLACE VIEW products  AS SELECT * FROM read_csv_auto('data/raw/olist_products_dataset.csv');
CREATE OR REPLACE VIEW customers AS SELECT * FROM read_csv_auto('data/raw/olist_customers_dataset.csv');
CREATE OR REPLACE VIEW xlate     AS SELECT * FROM read_csv_auto('data/raw/product_category_name_translation.csv');

-- Canonical product -> English category (manual labels for the 2 untranslated
-- categories; NULL category -> 'unknown'). Matches build_pipeline.py.
CREATE OR REPLACE VIEW product_category AS
SELECT p.product_id,
       CASE p.product_category_name
         WHEN 'pc_gamer' THEN 'gaming_pc'
         WHEN 'portateis_cozinha_e_preparadores_de_alimentos' THEN 'portable_kitchen_and_food_preparers'
         ELSE coalesce(x.product_category_name_english, 'unknown')
       END AS category_en
FROM products p
LEFT JOIN xlate x ON p.product_category_name = x.product_category_name;

-- Order grain: one row per order with product revenue, freight, delivery, review
CREATE OR REPLACE VIEW order_grain AS
WITH item_agg AS (
  SELECT order_id, sum(price) AS product_revenue, sum(freight_value) AS freight,
         count(*) AS n_items
  FROM items GROUP BY order_id),
rev_agg AS (
  SELECT order_id, avg(review_score) AS review_score,
         max(CASE WHEN review_comment_message IS NOT NULL THEN 1 ELSE 0 END) AS review_has_text
  FROM reviews GROUP BY order_id)
SELECT o.order_id, o.order_status, c.customer_unique_id, c.customer_state,
       o.order_purchase_timestamp,
       strftime(o.order_purchase_timestamp, '%Y-%m') AS purchase_ym,
       ia.product_revenue, ia.freight,
       coalesce(ia.product_revenue,0) + coalesce(ia.freight,0) AS order_value,
       ia.n_items,
       (o.order_status = 'delivered') AS delivered,
       (epoch(o.order_delivered_customer_date) - epoch(o.order_purchase_timestamp))/86400.0 AS delivery_days,
       (o.order_delivered_customer_date > o.order_estimated_delivery_date) AS is_late,
       ra.review_score, ra.review_has_text
FROM orders o
JOIN customers c USING (customer_id)
LEFT JOIN item_agg ia USING (order_id)
LEFT JOIN rev_agg  ra USING (order_id);

-- @label: Q1. Monthly orders + GMV (seasonality, Nov-2017 peak)
SELECT purchase_ym,
       count(DISTINCT order_id) AS orders,
       count(DISTINCT order_id) FILTER (WHERE delivered) AS delivered_orders,
       round(sum(product_revenue), 2) AS gmv
FROM order_grain
WHERE product_revenue IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- @label: Q2. Category revenue Pareto (top 15 + cumulative share)
WITH cat AS (
  SELECT pc.category_en, sum(i.price) AS revenue
  FROM items i JOIN product_category pc USING (product_id)
  GROUP BY 1)
SELECT category_en, round(revenue,2) AS revenue,
       round(100.0*revenue/sum(revenue) OVER (), 2) AS pct,
       round(100.0*sum(revenue) OVER (ORDER BY revenue DESC)/sum(revenue) OVER (), 2) AS cum_pct,
       row_number() OVER (ORDER BY revenue DESC) AS rank
FROM cat ORDER BY revenue DESC LIMIT 15;

-- @label: Q2b. How many categories make 80% of revenue
WITH cat AS (
  SELECT pc.category_en, sum(i.price) AS revenue
  FROM items i JOIN product_category pc USING (product_id) GROUP BY 1),
ranked AS (
  SELECT category_en, 100.0*sum(revenue) OVER (ORDER BY revenue DESC)/sum(revenue) OVER () AS cum_pct
  FROM cat)
SELECT count(*) FILTER (WHERE cum_pct <= 80) + 1 AS categories_for_80pct,
       count(*) AS total_categories FROM ranked;

-- @label: Q3. Delivery-time distribution + on-time rate
SELECT
  round(median(delivery_days), 2) AS median_days,
  round(quantile_cont(delivery_days, 0.90), 2) AS p90_days,
  round(100.0*count(*) FILTER (WHERE is_late = FALSE)/count(*) FILTER (WHERE delivery_days IS NOT NULL), 2) AS on_time_rate_pct,
  count(*) FILTER (WHERE delivery_days IS NOT NULL) AS delivered_with_dates
FROM order_grain;

-- @label: Q4. Review score vs delivery delay (the -0.334 relationship)
SELECT round(review_score) AS score,
       round(avg(delivery_days), 2) AS avg_delivery_days,
       round(100.0*avg(CASE WHEN is_late THEN 1.0 ELSE 0.0 END), 2) AS late_rate_pct,
       count(*) AS n
FROM order_grain
WHERE delivery_days IS NOT NULL AND review_score IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- @label: Q4b. Pearson r(delivery_days, review_score) on delivered orders
SELECT round(corr(delivery_days, review_score), 4) AS r, count(*) AS n
FROM order_grain WHERE delivery_days IS NOT NULL AND review_score IS NOT NULL;

-- @label: Q5. Customer repeat behaviour (acquisition vs retention)
WITH pc AS (
  SELECT customer_unique_id, count(DISTINCT order_id) AS orders, sum(order_value) AS monetary
  FROM order_grain GROUP BY 1)
SELECT CASE WHEN orders = 1 THEN '1' WHEN orders = 2 THEN '2' ELSE '3+' END AS orders_bucket,
       count(*) AS customers,
       round(100.0*count(*)/sum(count(*)) OVER (), 2) AS pct_customers,
       round(100.0*sum(monetary)/sum(sum(monetary)) OVER (), 2) AS pct_revenue
FROM pc GROUP BY 1 ORDER BY 1;

-- @label: Q6. Revenue concentration by state (SP dominance), top 10
SELECT customer_state,
       round(sum(product_revenue), 2) AS gmv,
       round(100.0*sum(product_revenue)/sum(sum(product_revenue)) OVER (), 2) AS pct_gmv,
       count(DISTINCT order_id) AS orders
FROM order_grain WHERE product_revenue IS NOT NULL
GROUP BY 1 ORDER BY gmv DESC LIMIT 10;

-- @label: Q7. Payment-type mix and installment behaviour
SELECT payment_type,
       count(*) AS payment_rows,
       round(100.0*count(*)/sum(count(*)) OVER (), 2) AS pct_rows,
       round(avg(payment_installments), 2) AS avg_installments,
       round(sum(payment_value), 2) AS total_value
FROM payments GROUP BY 1 ORDER BY total_value DESC;

-- @label: Q8. Raw-vs-decision-ready: the fan-out double-count
WITH naive AS (
  SELECT sum(i.price) AS naive_price, sum(p.payment_value) AS naive_pay, count(*) AS rows
  FROM orders o JOIN items i USING(order_id) JOIN payments p USING(order_id)),
correct AS (
  SELECT (SELECT sum(price) FROM items) AS gmv,
         (SELECT sum(payment_value) FROM payments) AS cash)
SELECT round(n.naive_price,2) AS naive_product_revenue,
       round(c.gmv,2)         AS decision_ready_gmv,
       round(100.0*(n.naive_price-c.gmv)/c.gmv,2) AS revenue_inflation_pct,
       round(n.naive_pay,2)   AS naive_cash,
       round(c.cash,2)        AS decision_ready_cash
FROM naive n, correct c;
