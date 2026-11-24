-- Silver: typed, de-duplicated tables with history across runs.

-- Changes: MERGE this run into the full history. New ids get first_seen_run; ids that drop out of the feed are kept
-- but flagged is_current = false, so nothing the firm was told about is ever lost.
MERGE INTO {{catalog}}.rcm_silver.changes AS t
USING (
  SELECT id, try_cast(published AS DATE) AS published, try_cast(nullif(first_seen, '') AS DATE) AS first_seen, source, feed,
         title, nullif(summary, '') AS summary, link, impact, try_cast(action_req AS INT) AS action_req,
         try_cast(nullif(deadline, '') AS DATE) AS deadline, status, try_cast(impact_sort AS INT) AS impact_sort, data_type,
         nullif(topics, '') AS topics, nullif(audiences, '') AS audiences, _run_date
  FROM {{catalog}}.rcm_bronze.changes
  WHERE _run_date = DATE '{{run_date}}'
  QUALIFY row_number() OVER (PARTITION BY id ORDER BY _loaded_at DESC) = 1
) AS s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET
  published = s.published, first_seen = s.first_seen, source = s.source, feed = s.feed, title = s.title, summary = s.summary,
  link = s.link, impact = s.impact, action_req = s.action_req, deadline = s.deadline, status = s.status,
  impact_sort = s.impact_sort, data_type = s.data_type, topics = s.topics, audiences = s.audiences,
  last_seen_run = s._run_date, is_current = TRUE
WHEN NOT MATCHED THEN INSERT (
  id, published, first_seen, source, feed, title, summary, link, impact, action_req, deadline, status, impact_sort, data_type,
  topics, audiences, first_seen_run, last_seen_run, is_current)
VALUES (
  s.id, s.published, s.first_seen, s.source, s.feed, s.title, s.summary, s.link, s.impact, s.action_req, s.deadline, s.status,
  s.impact_sort, s.data_type, s.topics, s.audiences, s._run_date, s._run_date, TRUE)
WHEN NOT MATCHED BY SOURCE AND t.is_current THEN UPDATE SET is_current = FALSE;

-- The costed view, one copy per run (this is what lets the report show backlog and slipping deadlines over time).
DELETE FROM {{catalog}}.rcm_silver.dashboard_history WHERE run_date = DATE '{{run_date}}';
INSERT INTO {{catalog}}.rcm_silver.dashboard_history
SELECT DATE '{{run_date}}', id, source, title, link, impact, try_cast(impact_sort AS INT), nullif(topics, ''), status,
       try_cast(action_req AS INT), try_cast(published AS DATE), try_cast(nullif(deadline, '') AS DATE),
       try_cast(one_off_hours AS DOUBLE), try_cast(ongoing_hours_yr AS DOUBLE), try_cast(external_one_off AS DOUBLE),
       try_cast(external_ongoing_yr AS DOUBLE), try_cast(internal_one_off_cost AS DOUBLE),
       try_cast(internal_ongoing_cost_yr AS DOUBLE), try_cast(total_one_off_cost AS DOUBLE),
       try_cast(total_ongoing_cost_yr AS DOUBLE), try_cast(target_date AS DATE), try_cast(lead_time_days AS INT),
       try_cast(days_left AS INT), work_status, try_cast(outstanding_hours AS DOUBLE), try_cast(at_risk AS INT),
       try_cast(as_of AS DATE), try_cast(nullif(first_seen, '') AS DATE), nullif(lead_role, ''), nullif(lead_department, '')
FROM {{catalog}}.rcm_bronze.dashboard_changes
WHERE _run_date = DATE '{{run_date}}'
QUALIFY row_number() OVER (PARTITION BY id ORDER BY _loaded_at DESC) = 1;

-- Source checks: the monitor's log file is cumulative, so only rows not loaded before are added.
MERGE INTO {{catalog}}.rcm_silver.run_log AS t
USING (
  SELECT DISTINCT try_cast(run_at AS TIMESTAMP) AS run_at, agency, feed, status, try_cast(items AS INT) AS items
  FROM {{catalog}}.rcm_bronze.run_log
  WHERE _run_date = DATE '{{run_date}}'
) AS s
ON t.run_at = s.run_at AND t.agency = s.agency AND t.feed = s.feed
WHEN NOT MATCHED THEN INSERT (run_at, run_date, agency, feed, status, ok, items)
VALUES (s.run_at, CAST(s.run_at AS DATE), s.agency, s.feed, s.status, left(s.status, 2) = 'ok', s.items);
