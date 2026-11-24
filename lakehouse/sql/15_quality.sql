-- Data quality gate on this run's bronze rows. Blocking checks stop the load before silver is touched
-- (the runner reads the result and fails the job); warnings are recorded and the load carries on.

DELETE FROM {{catalog}}.rcm_silver.quality_checks WHERE run_date = DATE '{{run_date}}';

INSERT INTO {{catalog}}.rcm_silver.quality_checks
SELECT DATE '{{run_date}}', check_name, blocking, failed_rows, failed_rows = 0, current_timestamp()
FROM (
  SELECT 'changes: id present' AS check_name, TRUE AS blocking,
         COUNT_IF(id IS NULL OR trim(id) = '') AS failed_rows
  FROM {{catalog}}.rcm_bronze.changes WHERE _run_date = DATE '{{run_date}}'
  UNION ALL
  SELECT 'changes: id unique', TRUE, COUNT(*)
  FROM (SELECT id FROM {{catalog}}.rcm_bronze.changes WHERE _run_date = DATE '{{run_date}}' GROUP BY id HAVING COUNT(*) > 1) d
  UNION ALL
  SELECT 'changes: published is a date', TRUE, COUNT_IF(try_cast(published AS DATE) IS NULL)
  FROM {{catalog}}.rcm_bronze.changes WHERE _run_date = DATE '{{run_date}}'
  UNION ALL
  SELECT 'changes: impact is High/Medium/Low', FALSE, COUNT_IF(impact IS NULL OR impact NOT IN ('High', 'Medium', 'Low'))
  FROM {{catalog}}.rcm_bronze.changes WHERE _run_date = DATE '{{run_date}}'
  UNION ALL
  SELECT 'changes: deadline not before published', FALSE,
         COUNT_IF(try_cast(nullif(deadline, '') AS DATE) < try_cast(published AS DATE))
  FROM {{catalog}}.rcm_bronze.changes WHERE _run_date = DATE '{{run_date}}'
  UNION ALL
  SELECT 'dashboard: every change is costed', TRUE, COUNT(*)
  FROM {{catalog}}.rcm_bronze.changes c
  LEFT JOIN (SELECT id FROM {{catalog}}.rcm_bronze.dashboard_changes WHERE _run_date = DATE '{{run_date}}') d ON c.id = d.id
  WHERE c._run_date = DATE '{{run_date}}' AND d.id IS NULL
  UNION ALL
  SELECT 'topics: refer to a known change', FALSE, COUNT(*)
  FROM {{catalog}}.rcm_bronze.change_topics t
  LEFT JOIN (SELECT id FROM {{catalog}}.rcm_bronze.changes WHERE _run_date = DATE '{{run_date}}') c ON t.id = c.id
  WHERE t._run_date = DATE '{{run_date}}' AND c.id IS NULL
  UNION ALL
  SELECT 'effort: hours not negative', FALSE, COUNT_IF(try_cast(one_off_hours AS DOUBLE) < 0 OR try_cast(ongoing_hours_yr AS DOUBLE) < 0)
  FROM {{catalog}}.rcm_bronze.change_effort WHERE _run_date = DATE '{{run_date}}'
  UNION ALL
  SELECT 'run log: at least one source checked', FALSE, CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
  FROM {{catalog}}.rcm_bronze.run_log WHERE _run_date = DATE '{{run_date}}'
) checks;
