-- PeoplePulse MIS views (REAL IBM HR Analytics Attrition data).
--
-- PORTABILITY: these run unchanged on SQLite (local) and PostgreSQL (CI).
-- Rules we follow so one file serves both dialects:
--   * float division via `100.0 * ...`, guarded with NULLIF(denominator, 0);
--   * no 2-argument ROUND on floats (Postgres lacks ROUND(double, int)) --
--     rounding for display happens in the app layer;
--   * only CASE / GROUP BY / standard aggregates (portable everywhere).
--
-- The data is cross-sectional (one row per employee, with an attrition outcome),
-- so every view is a cross-sectional cut of attrition / headcount / pay. There
-- are no time-series or hiring-funnel views because the source has no dates.
--
-- `attrition` is 1 (left) and 0 (stayed), so SUM(attrition) counts leavers.
-- The GenAI query API (api/guardrails.py) only ever queries these v_* views.

-- 1. Company-wide attrition.
CREATE VIEW v_attrition_overall AS
SELECT COUNT(*)                                            AS total_employees,
       SUM(attrition)                                      AS leavers,
       100.0 * SUM(attrition) / NULLIF(COUNT(*), 0)        AS attrition_pct
FROM dim_employee;

-- 2. Attrition by department.
CREATE VIEW v_attrition_by_department AS
SELECT dep.department_name,
       dep.function_group,
       COUNT(*)                                            AS employees,
       SUM(e.attrition)                                    AS leavers,
       100.0 * SUM(e.attrition) / NULLIF(COUNT(*), 0)      AS attrition_pct
FROM dim_employee e
JOIN dim_department dep ON dep.department_key = e.department_key
GROUP BY dep.department_name, dep.function_group;

-- 3. Attrition by job role.
CREATE VIEW v_attrition_by_job_role AS
SELECT r.job_role,
       r.department_name,
       COUNT(*)                                            AS employees,
       SUM(e.attrition)                                    AS leavers,
       100.0 * SUM(e.attrition) / NULLIF(COUNT(*), 0)      AS attrition_pct
FROM dim_employee e
JOIN dim_job_role r ON r.job_role_key = e.job_role_key
GROUP BY r.job_role, r.department_name;

-- 4. Attrition by overtime (the single strongest driver in this dataset).
CREATE VIEW v_attrition_by_overtime AS
SELECT e.overtime,
       COUNT(*)                                            AS employees,
       SUM(e.attrition)                                    AS leavers,
       100.0 * SUM(e.attrition) / NULLIF(COUNT(*), 0)      AS attrition_pct
FROM dim_employee e
GROUP BY e.overtime;

-- 5. Attrition by job level (1 junior .. 5 senior).
CREATE VIEW v_attrition_by_job_level AS
SELECT e.job_level,
       COUNT(*)                                            AS employees,
       SUM(e.attrition)                                    AS leavers,
       100.0 * SUM(e.attrition) / NULLIF(COUNT(*), 0)      AS attrition_pct
FROM dim_employee e
GROUP BY e.job_level;

-- 6. Attrition by tenure (years at company) bucket.
CREATE VIEW v_attrition_by_tenure_bucket AS
WITH b AS (
    SELECT attrition,
           CASE
               WHEN years_at_company <= 2  THEN '0-2y'
               WHEN years_at_company <= 5  THEN '3-5y'
               WHEN years_at_company <= 10 THEN '6-10y'
               ELSE '10y+'
           END AS tenure_bucket,
           CASE
               WHEN years_at_company <= 2  THEN 1
               WHEN years_at_company <= 5  THEN 2
               WHEN years_at_company <= 10 THEN 3
               ELSE 4
           END AS bucket_order
    FROM fact_employee
)
SELECT tenure_bucket,
       bucket_order,
       COUNT(*)                                            AS employees,
       SUM(attrition)                                      AS leavers,
       100.0 * SUM(attrition) / NULLIF(COUNT(*), 0)        AS attrition_pct
FROM b
GROUP BY tenure_bucket, bucket_order;

-- 7. Attrition by monthly-income band.
CREATE VIEW v_attrition_by_income_band AS
WITH b AS (
    SELECT attrition,
           CASE
               WHEN monthly_income < 3000  THEN '<3k'
               WHEN monthly_income < 5000  THEN '3k-5k'
               WHEN monthly_income < 10000 THEN '5k-10k'
               ELSE '10k+'
           END AS income_band,
           CASE
               WHEN monthly_income < 3000  THEN 1
               WHEN monthly_income < 5000  THEN 2
               WHEN monthly_income < 10000 THEN 3
               ELSE 4
           END AS band_order
    FROM fact_employee
)
SELECT income_band,
       band_order,
       COUNT(*)                                            AS employees,
       SUM(attrition)                                      AS leavers,
       100.0 * SUM(attrition) / NULLIF(COUNT(*), 0)        AS attrition_pct
FROM b
GROUP BY income_band, band_order;

-- 8. Attrition by age band.
CREATE VIEW v_attrition_by_age_band AS
WITH b AS (
    SELECT attrition,
           CASE
               WHEN age < 30 THEN '<30'
               WHEN age < 40 THEN '30-39'
               WHEN age < 50 THEN '40-49'
               ELSE '50+'
           END AS age_band,
           CASE
               WHEN age < 30 THEN 1
               WHEN age < 40 THEN 2
               WHEN age < 50 THEN 3
               ELSE 4
           END AS band_order
    FROM dim_employee
)
SELECT age_band,
       band_order,
       COUNT(*)                                            AS employees,
       SUM(attrition)                                      AS leavers,
       100.0 * SUM(attrition) / NULLIF(COUNT(*), 0)        AS attrition_pct
FROM b
GROUP BY age_band, band_order;

-- 9. Average satisfaction scores, stayers vs leavers.
CREATE VIEW v_satisfaction_by_attrition AS
SELECT attrition,
       COUNT(*)                          AS employees,
       AVG(job_satisfaction)             AS avg_job_satisfaction,
       AVG(environment_satisfaction)     AS avg_environment_satisfaction,
       AVG(work_life_balance)            AS avg_work_life_balance,
       AVG(job_involvement)              AS avg_job_involvement
FROM fact_employee
GROUP BY attrition;

-- 10. Average monthly income by department.
CREATE VIEW v_income_by_department AS
SELECT dep.department_name,
       COUNT(*)                          AS employees,
       AVG(f.monthly_income)             AS avg_monthly_income
FROM fact_employee f
JOIN dim_department dep ON dep.department_key = f.department_key
GROUP BY dep.department_name;

-- 11. Gender diversity by department.
CREATE VIEW v_gender_diversity AS
SELECT dep.department_name,
       SUM(CASE WHEN e.gender = 'Female' THEN 1 ELSE 0 END) AS female_headcount,
       SUM(CASE WHEN e.gender = 'Male'   THEN 1 ELSE 0 END) AS male_headcount,
       COUNT(*)                                             AS total_headcount,
       100.0 * SUM(CASE WHEN e.gender = 'Female' THEN 1 ELSE 0 END)
           / NULLIF(COUNT(*), 0)                            AS female_pct
FROM dim_employee e
JOIN dim_department dep ON dep.department_key = e.department_key
GROUP BY dep.department_name;
