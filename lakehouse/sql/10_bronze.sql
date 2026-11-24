-- Bronze: land this run's CSV files unchanged (all text), tagged with the run date.
-- Delete-then-insert makes a re-run of the same date replace, not duplicate, its rows.
-- {{src:name}} reads <landing>/<run date>/<name>.csv (read_files on Databricks).

DELETE FROM {{catalog}}.rcm_bronze.changes WHERE _run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_bronze.changes
SELECT id, published, first_seen, source, feed, title, summary, link, impact, action_req, deadline, status, impact_sort,
       data_type, topics, audiences, DATE '{{run_date}}', current_timestamp()
FROM {{src:changes}};

DELETE FROM {{catalog}}.rcm_bronze.change_topics WHERE _run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_bronze.change_topics
SELECT id, topic, DATE '{{run_date}}', current_timestamp() FROM {{src:change_topics}};

DELETE FROM {{catalog}}.rcm_bronze.change_audiences WHERE _run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_bronze.change_audiences
SELECT id, audience, DATE '{{run_date}}', current_timestamp() FROM {{src:change_audiences}};

DELETE FROM {{catalog}}.rcm_bronze.dim_date WHERE _run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_bronze.dim_date
SELECT `date`, year, month_num, month_name, year_month, month_start, week_start, DATE '{{run_date}}', current_timestamp()
FROM {{src:dim_date}};

DELETE FROM {{catalog}}.rcm_bronze.dashboard_changes WHERE _run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_bronze.dashboard_changes
SELECT id, source, title, link, impact, impact_sort, topics, status, action_req, published, deadline, one_off_hours,
       ongoing_hours_yr, external_one_off, external_ongoing_yr, internal_one_off_cost, internal_ongoing_cost_yr,
       total_one_off_cost, total_ongoing_cost_yr, target_date, lead_time_days, days_left, work_status, outstanding_hours,
       at_risk, as_of, first_seen, lead_role, lead_department, DATE '{{run_date}}', current_timestamp()
FROM {{src:dashboard_changes}};

DELETE FROM {{catalog}}.rcm_bronze.change_effort WHERE _run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_bronze.change_effort
SELECT id, role, one_off_hours, ongoing_hours_yr, one_off_cost, ongoing_cost_yr, department, hourly_cost,
       DATE '{{run_date}}', current_timestamp()
FROM {{src:change_effort}};

DELETE FROM {{catalog}}.rcm_bronze.capacity_monthly WHERE _run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_bronze.capacity_monthly
SELECT month_start, role, hours_required, hours_available, load_pct, hours_over_capacity, DATE '{{run_date}}', current_timestamp()
FROM {{src:capacity_monthly}};

DELETE FROM {{catalog}}.rcm_bronze.run_log WHERE _run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_bronze.run_log
SELECT run_at, agency, feed, status, items, DATE '{{run_date}}', current_timestamp() FROM {{src:run_log}};
