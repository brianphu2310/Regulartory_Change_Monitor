# Architecture and design decisions

## 1. Requirements

**Functional**

| # | The system must | Delivered by |
|---|---|---|
| F1 | Collect new announcements from official Australian agencies without manual checking | `monitor/fetch.py`, `monitor/sources.py` |
| F2 | Ignore what it has already seen and what is not relevant to a law firm | `seen.csv`, `classifier.py` (topic "Other" is dropped) |
| F3 | Tag each change: topic, impact, audience, action required, deadline | `classifier.py` |
| F4 | Estimate the cost, staff hours, owner and capacity load of each change | `impact_model.py` |
| F5 | Tell someone when something new arrives | GitHub Issue with `reports/latest.md` |
| F6 | Give a manager a dashboard they can read without help | Power BI: `powerbi/live/` |

**Non-functional**

| Need | Target | Why |
|---|---|---|
| Cost | $0 to run, indefinitely | A portfolio project must still work in a year, after every trial has ended |
| Cadence | Weekly (Monday 07:17 Sydney) | Changes arrive a few times a week; the firm decides in a weekly meeting |
| Reliability | One failing source never stops the run | Agency sites change layout and block traffic |
| Auditability | Every figure traceable to a rule or a commit | Compliance work is reviewed; "the model said so" is not an answer |
| Good citizenship | robots.txt respected, identifying user agent, one request per page | Government sites are public infrastructure |

**Constraints:** one person, no budget, no cloud account that outlives a trial, Power BI Desktop on Windows.

## 2. High-level design

```
                ┌──────────────────── GitHub (repo = code + data + history) ─────────────────────┐
  Monday 07:17  │                                                                                 │
  cron ───────► │  Actions ─► docker build ─► docker run reg-monitor                              │
                │                               │                                                 │
                │          ┌────────────────────┼──────────────────────────┐                      │
                │          ▼                    ▼                          ▼                      │
                │   fetch (RSS → page)    classify (rules)        impact model (rules)            │
                │   robots.txt check      topic, impact,          hours × rate + external,        │
                │   per-source errors     action, deadline        target date, capacity           │
                │          └────────────────────┬──────────────────────────┘                      │
                │                               ▼                                                 │
                │            data/live/*.csv  +  reports/latest.md   ──► git commit               │
                │                               │                                                 │
                │              new relevant > 0 ├──► GitHub Issue (email to the owner)            │
                └───────────────────────────────┼─────────────────────────────────────────────────┘
                                                ▼
                     Power BI Desktop ── HTTPS (raw.githubusercontent.com) ── Refresh
```

## 3. Data model

One wide fact table for the dashboard plus three supporting tables, all CSV, same schema for sample (`bi_export/`)
and live (`data/live/`) data so the report switches with one parameter.

| Table | Grain | Key columns |
|---|---|---|
| `dashboard_changes` | one row per change | id, source, title, impact, topics, target_date, days_left, total_one_off_cost, outstanding_hours, lead_role |
| `change_effort` | change × role | id, role, one_off_hours, one_off_cost, department |
| `capacity_monthly` | month × role | month_start, role, hours_required, hours_available, load_pct |
| `run_log` | run × source | run_at, agency, status, items |

Relationship: `change_effort[id]` many-to-one `dashboard_changes[id]`. The other tables are filtered on their own
columns. Normalised tables (`changes`, `change_topics`, `change_audiences`) are kept for the v1 star schema.

## 4. Deep dive

**Fetching.** Each source tries its RSS feed, then its news listing page with a link pattern. The fetcher checks
robots.txt first and returns a status instead of raising, so the run log records "ok via page (10 items)",
"403 Forbidden" or "skipped (robots.txt)" per source.

**De-duplication.** An item's id is the first 16 hex characters of SHA-1 of its normalised link. `seen.csv` holds every
id ever fetched, relevant or not, so an item is processed once. The first run is a baseline: it loads and flags nothing.

**Idempotency.** Re-running in the same week adds no changes: only the run log gains a row, so the commit is small and
no issue is opened.

**Errors.** Network errors, 403s, timeouts and layout changes are caught per source. A failure shows in the run log, the
report's Source health table and the Power BI Capacity & sources page; the run still succeeds.

## 5. Trade-offs

| Decision | Chosen | Alternative | Why this one | What it costs |
|---|---|---|---|---|
| Orchestration | GitHub Actions cron | n8n Cloud, Airflow | Free forever for a public repo, lives next to the code, logs kept | No visual workflow editor |
| Packaging | Docker image | Plain `pip install` in the runner | Same run on a laptop (`run_local.ps1`) and in the cloud | ~30 s build per run |
| Storage | CSV in Git | Snowflake, Supabase/Postgres | Free, versioned, diffable; every week is a commit | Not for millions of rows or concurrent writers |
| Alerting | GitHub Issue | Email via SMTP, Teams | No secrets to store; GitHub emails the owner | Recipients need a GitHub account |
| Classification | Keyword rules | ML / LLM classifier | Explainable and testable; an auditor can read the rule | Misses wording the rules do not cover |
| BI | Power BI Desktop, PBIP in Git | Power BI Service, Tableau Public | Report defined as code and reviewable; no tenant needed | Refresh is a button press, not scheduled |
| Cadence | Weekly | Daily | Matches how the firm decides; less load on agency sites | A Tuesday announcement waits until Monday (manual run available) |

## 6. Scale and reliability

About 10 to 60 items a week across six sources; a run takes under two minutes including the Docker build. The CSVs grow
by a few kilobytes a week, so Git storage is not a concern for years. The weakest link is source availability: from
GitHub's runners, Treasury answers, while AUSTRAC and Fair Work time out and the ATO and OAIC return 403
(tested 20 Nov 2026). Desktop runs reach them.

## 7. What I would revisit as it grows

- **More sources or daily runs:** move storage from CSV to Postgres (e.g. Supabase) and keep CSV exports for BI.
- **Blocked sources:** a self-hosted Actions runner on an office machine, with the organisation's permission, instead of any workaround.
- **Better tagging:** keep the rules as the baseline and add an LLM pass whose output must cite the sentence it relied on, scored against a hand-labelled set.
- **Scheduled refresh:** publish to Power BI Service once a licensed workspace exists.
