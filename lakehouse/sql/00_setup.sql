-- Regulatory Change Monitor lakehouse: schemas, landing volume and tables.
-- Runs on a Databricks SQL warehouse (Unity Catalog). {{catalog}} is the catalog ("workspace" on Free Edition).
-- Every statement is idempotent, so the whole file runs before each load.

CREATE SCHEMA IF NOT EXISTS {{catalog}}.rcm_bronze COMMENT 'Raw CSV rows exactly as the weekly monitor wrote them, one copy per run';
CREATE SCHEMA IF NOT EXISTS {{catalog}}.rcm_silver COMMENT 'Typed, de-duplicated and checked tables; history kept across runs';
CREATE SCHEMA IF NOT EXISTS {{catalog}}.rcm_gold COMMENT 'Tables the Power BI report reads, plus the weekly snapshot';

-- @remote  (the landing folder only exists on Databricks; the local test engine reads the CSVs in place)
CREATE VOLUME IF NOT EXISTS {{catalog}}.rcm_bronze.landing COMMENT 'CSV files uploaded by GitHub Actions, one folder per run date';

-- ------------------------------------------------------------------ bronze: every column as text + load metadata
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_bronze.changes (
  id STRING, published STRING, first_seen STRING, source STRING, feed STRING, title STRING, summary STRING, link STRING,
  impact STRING, action_req STRING, deadline STRING, status STRING, impact_sort STRING, data_type STRING, topics STRING,
  audiences STRING, _run_date DATE, _loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_bronze.change_topics (id STRING, topic STRING, _run_date DATE, _loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_bronze.change_audiences (id STRING, audience STRING, _run_date DATE, _loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_bronze.dim_date (
  `date` STRING, year STRING, month_num STRING, month_name STRING, year_month STRING, month_start STRING, week_start STRING,
  _run_date DATE, _loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_bronze.dashboard_changes (
  id STRING, source STRING, title STRING, link STRING, impact STRING, impact_sort STRING, topics STRING, status STRING,
  action_req STRING, published STRING, deadline STRING, one_off_hours STRING, ongoing_hours_yr STRING, external_one_off STRING,
  external_ongoing_yr STRING, internal_one_off_cost STRING, internal_ongoing_cost_yr STRING, total_one_off_cost STRING,
  total_ongoing_cost_yr STRING, target_date STRING, lead_time_days STRING, days_left STRING, work_status STRING,
  outstanding_hours STRING, at_risk STRING, as_of STRING, first_seen STRING, lead_role STRING, lead_department STRING,
  _run_date DATE, _loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_bronze.change_effort (
  id STRING, role STRING, one_off_hours STRING, ongoing_hours_yr STRING, one_off_cost STRING, ongoing_cost_yr STRING,
  department STRING, hourly_cost STRING, _run_date DATE, _loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_bronze.capacity_monthly (
  month_start STRING, role STRING, hours_required STRING, hours_available STRING, load_pct STRING, hours_over_capacity STRING,
  _run_date DATE, _loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_bronze.run_log (
  run_at STRING, agency STRING, feed STRING, status STRING, items STRING, _run_date DATE, _loaded_at TIMESTAMP);

-- ------------------------------------------------------------------ silver
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_silver.changes (
  id STRING NOT NULL, published DATE, first_seen DATE, source STRING, feed STRING, title STRING, summary STRING, link STRING,
  impact STRING, action_req INT, deadline DATE, status STRING, impact_sort INT, data_type STRING, topics STRING, audiences STRING,
  first_seen_run DATE, last_seen_run DATE, is_current BOOLEAN)
  COMMENT 'One row per regulatory change ever seen; MERGE keeps first_seen_run and flags changes no longer in the feed';
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_silver.dashboard_history (
  run_date DATE, id STRING, source STRING, title STRING, link STRING, impact STRING, impact_sort INT, topics STRING,
  status STRING, action_req INT, published DATE, deadline DATE, one_off_hours DOUBLE, ongoing_hours_yr DOUBLE,
  external_one_off DOUBLE, external_ongoing_yr DOUBLE, internal_one_off_cost DOUBLE, internal_ongoing_cost_yr DOUBLE,
  total_one_off_cost DOUBLE, total_ongoing_cost_yr DOUBLE, target_date DATE, lead_time_days INT, days_left INT,
  work_status STRING, outstanding_hours DOUBLE, at_risk INT, as_of DATE, first_seen DATE, lead_role STRING, lead_department STRING)
  COMMENT 'The costed view of every change, kept for every run, so slipping deadlines and backlog can be tracked';
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_silver.run_log (
  run_at TIMESTAMP, run_date DATE, agency STRING, feed STRING, status STRING, ok BOOLEAN, items INT)
  COMMENT 'Every source check of every run';
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_silver.quality_checks (
  run_date DATE, check_name STRING, blocking BOOLEAN, failed_rows BIGINT, passed BOOLEAN, checked_at TIMESTAMP)
  COMMENT 'Data quality results for each run; the load stops if a blocking check fails';

-- ------------------------------------------------------------------ gold history
CREATE TABLE IF NOT EXISTS {{catalog}}.rcm_gold.weekly_snapshot (
  run_date DATE, changes_on_file BIGINT, new_this_run BIGINT, high_impact BIGINT, needs_action BIGINT,
  past_target_date BIGINT, one_off_cost DOUBLE, ongoing_cost_yr DOUBLE, backlog_hours DOUBLE, peak_month_load DOUBLE,
  sources_checked BIGINT, sources_ok BIGINT)
  COMMENT 'One row per weekly run: the numbers on the report front page, over time';
