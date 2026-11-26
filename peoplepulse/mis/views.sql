-- PeoplePulse MIS views.
--
-- PORTABILITY: these run unchanged on SQLite (local) and PostgreSQL (CI).
-- Rules we follow so one file serves both dialects:
--   * no dialect-specific date functions -- all date parts come from dim_date;
--   * float division via `100.0 * ...` and guarded with NULLIF(denominator, 0);
--   * no 2-argument ROUND on floats (Postgres lacks ROUND(double, int)) --
--     rounding for display happens in the app layer;
--   * CTEs, LAG(), and framed window aggregates are standard in both.
--
-- The GenAI query API (api/guardrails.py) only ever queries these v_* views.

-- 1. Headcount at full grain (month x department x country x grade x gender).
CREATE VIEW v_headcount_monthly AS
SELECT d.date_key,
       d.year_month,
       d.year,
       d.month,
       dep.department_name,
       co.country_name,
       co.region,
       f.grade,
       f.gender,
       f.headcount
FROM fact_headcount_monthly f
JOIN dim_date d         ON d.date_key = f.date_key
JOIN dim_department dep ON dep.department_key = f.department_key
JOIN dim_country co     ON co.country_key = f.country_key;

-- 2. Total company headcount per month (the trend line).
CREATE VIEW v_headcount_trend AS
SELECT d.date_key,
       d.year_month,
       SUM(f.headcount) AS total_headcount
FROM fact_headcount_monthly f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY d.date_key, d.year_month;

-- 3. Monthly attrition and rolling-12-month (annualised) attrition.
--    monthly % = exits / average(begin, end headcount)
--    rolling % = sum of exits over 12 months / average monthly headcount over 12 months
CREATE VIEW v_attrition_monthly AS
WITH hc AS (
    SELECT date_key, SUM(headcount) AS end_headcount
    FROM fact_headcount_monthly
    GROUP BY date_key
),
ex AS (
    SELECT date_key, COUNT(*) AS exits
    FROM fact_exits
    GROUP BY date_key
),
m AS (
    SELECT hc.date_key,
           hc.end_headcount,
           COALESCE(ex.exits, 0) AS exits,
           LAG(hc.end_headcount) OVER (ORDER BY hc.date_key) AS prev_headcount
    FROM hc
    LEFT JOIN ex ON ex.date_key = hc.date_key
)
SELECT m.date_key,
       d.year_month,
       m.exits,
       m.end_headcount,
       COALESCE(m.prev_headcount, m.end_headcount) AS begin_headcount,
       100.0 * m.exits
           / NULLIF((m.end_headcount + COALESCE(m.prev_headcount, m.end_headcount)) / 2.0, 0)
           AS monthly_attrition_pct,
       100.0 * SUM(m.exits) OVER w
           / NULLIF(AVG(m.end_headcount) OVER w, 0)
           AS rolling_12m_attrition_pct
FROM m
JOIN dim_date d ON d.date_key = m.date_key
WINDOW w AS (ORDER BY m.date_key ROWS BETWEEN 11 PRECEDING AND CURRENT ROW);

-- 4. Voluntary vs involuntary exits per month.
CREATE VIEW v_exits_by_type AS
SELECT d.year_month,
       fe.exit_type,
       COUNT(*) AS exits
FROM fact_exits fe
JOIN dim_date d ON d.date_key = fe.date_key
GROUP BY d.year_month, fe.exit_type;

-- 5. Exit reasons as a share of all exits.
CREATE VIEW v_exit_reasons AS
SELECT fe.exit_type,
       fe.exit_reason,
       COUNT(*) AS exits,
       100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM fact_exits), 0) AS pct_of_all_exits
FROM fact_exits fe
GROUP BY fe.exit_type, fe.exit_reason;

-- 6. Tenure-at-exit buckets.
CREATE VIEW v_tenure_buckets AS
WITH b AS (
    SELECT tenure_days,
           CASE
               WHEN tenure_days < 365  THEN '0-1y'
               WHEN tenure_days < 730  THEN '1-2y'
               WHEN tenure_days < 1095 THEN '2-3y'
               WHEN tenure_days < 1825 THEN '3-5y'
               ELSE '5y+'
           END AS tenure_bucket,
           CASE
               WHEN tenure_days < 365  THEN 1
               WHEN tenure_days < 730  THEN 2
               WHEN tenure_days < 1095 THEN 3
               WHEN tenure_days < 1825 THEN 4
               ELSE 5
           END AS bucket_order
    FROM fact_exits
)
SELECT tenure_bucket,
       bucket_order,
       COUNT(*) AS exits,
       AVG(tenure_days) AS avg_tenure_days
FROM b
GROUP BY tenure_bucket, bucket_order;

-- 7. Time-to-hire (hire-weighted average) per month / department / country.
CREATE VIEW v_time_to_hire AS
SELECT d.year_month,
       dep.department_name,
       co.country_name,
       SUM(ff.hires) AS hires,
       SUM(ff.avg_time_to_hire_days * ff.hires) / NULLIF(SUM(ff.hires), 0)
           AS avg_time_to_hire_days
FROM fact_hiring_funnel ff
JOIN dim_date d         ON d.date_key = ff.date_key
JOIN dim_department dep ON dep.department_key = ff.department_key
JOIN dim_country co     ON co.country_key = ff.country_key
GROUP BY d.year_month, dep.department_name, co.country_name;

-- 8. Offer-acceptance rate per month / department / country.
CREATE VIEW v_offer_acceptance AS
SELECT d.year_month,
       dep.department_name,
       co.country_name,
       SUM(ff.offers) AS offers,
       SUM(ff.accepts) AS accepts,
       100.0 * SUM(ff.accepts) / NULLIF(SUM(ff.offers), 0) AS offer_acceptance_pct
FROM fact_hiring_funnel ff
JOIN dim_date d         ON d.date_key = ff.date_key
JOIN dim_department dep ON dep.department_key = ff.department_key
JOIN dim_country co     ON co.country_key = ff.country_key
GROUP BY d.year_month, dep.department_name, co.country_name;

-- 9. Gender diversity by grade (latest monthly snapshot).
CREATE VIEW v_gender_diversity_by_grade AS
WITH latest AS (
    SELECT MAX(date_key) AS dk FROM fact_headcount_monthly
)
SELECT f.grade,
       SUM(CASE WHEN f.gender = 'F' THEN f.headcount ELSE 0 END) AS female_headcount,
       SUM(CASE WHEN f.gender = 'M' THEN f.headcount ELSE 0 END) AS male_headcount,
       SUM(f.headcount) AS total_headcount,
       100.0 * SUM(CASE WHEN f.gender = 'F' THEN f.headcount ELSE 0 END)
           / NULLIF(SUM(f.headcount), 0) AS female_pct
FROM fact_headcount_monthly f
CROSS JOIN latest
WHERE f.date_key = latest.dk
GROUP BY f.grade;
