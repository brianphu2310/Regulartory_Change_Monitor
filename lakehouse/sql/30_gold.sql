-- Gold: the tables Power BI reads (same names and columns as the CSV files, typed) and the weekly snapshot.

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.changes AS
SELECT id, published, first_seen, source, feed, title, summary, link, impact, action_req, deadline, status, impact_sort,
       data_type, topics, audiences, first_seen_run, last_seen_run
FROM {{catalog}}.rcm_silver.changes
WHERE is_current;

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.change_topics AS
SELECT DISTINCT id, topic FROM {{catalog}}.rcm_bronze.change_topics WHERE _run_date = DATE '{{run_date}}' AND topic <> '';

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.change_audiences AS
SELECT DISTINCT id, audience FROM {{catalog}}.rcm_bronze.change_audiences WHERE _run_date = DATE '{{run_date}}' AND audience <> '';

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.dim_date AS
SELECT DISTINCT try_cast(`date` AS DATE) AS `date`, try_cast(year AS INT) AS year, try_cast(month_num AS INT) AS month_num,
       month_name, year_month, try_cast(month_start AS DATE) AS month_start, try_cast(week_start AS DATE) AS week_start
FROM {{catalog}}.rcm_bronze.dim_date
WHERE _run_date = DATE '{{run_date}}';

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.dashboard_changes AS
SELECT id, source, title, link, impact, impact_sort, topics, status, action_req, published, deadline, one_off_hours,
       ongoing_hours_yr, external_one_off, external_ongoing_yr, internal_one_off_cost, internal_ongoing_cost_yr,
       total_one_off_cost, total_ongoing_cost_yr, target_date, lead_time_days, days_left, work_status, outstanding_hours,
       at_risk, as_of, first_seen, lead_role, lead_department
FROM {{catalog}}.rcm_silver.dashboard_history
WHERE run_date = DATE '{{run_date}}';

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.change_effort AS
SELECT id, role, try_cast(one_off_hours AS DOUBLE) AS one_off_hours, try_cast(ongoing_hours_yr AS DOUBLE) AS ongoing_hours_yr,
       try_cast(one_off_cost AS DOUBLE) AS one_off_cost, try_cast(ongoing_cost_yr AS DOUBLE) AS ongoing_cost_yr, department,
       try_cast(hourly_cost AS DOUBLE) AS hourly_cost
FROM {{catalog}}.rcm_bronze.change_effort
WHERE _run_date = DATE '{{run_date}}';

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.capacity_monthly AS
SELECT try_cast(month_start AS DATE) AS month_start, role, try_cast(hours_required AS DOUBLE) AS hours_required,
       try_cast(hours_available AS DOUBLE) AS hours_available, try_cast(load_pct AS DOUBLE) AS load_pct,
       try_cast(hours_over_capacity AS DOUBLE) AS hours_over_capacity
FROM {{catalog}}.rcm_bronze.capacity_monthly
WHERE _run_date = DATE '{{run_date}}';

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.run_log AS
SELECT run_at, agency, feed, status, items FROM {{catalog}}.rcm_silver.run_log;

CREATE OR REPLACE TABLE {{catalog}}.rcm_gold.quality_checks AS
SELECT * FROM {{catalog}}.rcm_silver.quality_checks;

-- One row per run with the front-page numbers, so the report can show them over time.
DELETE FROM {{catalog}}.rcm_gold.weekly_snapshot WHERE run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_gold.weekly_snapshot
SELECT DATE '{{run_date}}' AS run_date,
       COUNT(*) AS changes_on_file,
       COUNT_IF(d.first_seen > DATE '{{run_date}}' - INTERVAL 7 DAYS) AS new_this_run,
       COUNT_IF(d.impact = 'High') AS high_impact,
       COUNT_IF(d.work_status = 'Outstanding') AS needs_action,
       COUNT_IF(d.work_status = 'Outstanding' AND d.days_left < 0) AS past_target_date,
       SUM(d.total_one_off_cost) AS one_off_cost,
       SUM(d.total_ongoing_cost_yr) AS ongoing_cost_yr,
       SUM(d.outstanding_hours) AS backlog_hours,
       (SELECT MAX(need / avail) FROM (
          SELECT month_start, SUM(hours_required) AS need, SUM(hours_available) AS avail
          FROM {{catalog}}.rcm_gold.capacity_monthly GROUP BY month_start) m WHERE avail > 0) AS peak_month_load,
       (SELECT COUNT(*) FROM {{catalog}}.rcm_silver.run_log r
         WHERE r.run_date = (SELECT MAX(run_date) FROM {{catalog}}.rcm_silver.run_log WHERE run_date <= DATE '{{run_date}}')) AS sources_checked,
       COALESCE((SELECT COUNT_IF(ok) FROM {{catalog}}.rcm_silver.run_log r
         WHERE r.run_date = (SELECT MAX(run_date) FROM {{catalog}}.rcm_silver.run_log WHERE run_date <= DATE '{{run_date}}')), 0) AS sources_ok
FROM {{catalog}}.rcm_silver.dashboard_history d
WHERE d.run_date = DATE '{{run_date}}';
