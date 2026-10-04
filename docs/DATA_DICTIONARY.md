# Data dictionary

All rows are synthetic (`data_type = Sample`). Tables are in `bi_export/`.

| Table | Rows | Grain | Key |
|---|---|---|---|
| `changes` | 200 | one regulatory change | `id` |
| `change_topics` | 283 | one topic tag on one change | (`id`, `topic`) |
| `change_audiences` | 271 | one affected audience on one change | (`id`, `audience`) |
| `change_departments` | 303 | one department a change lands in | (`id`, `department`) |
| `dim_topic_department` | 11 | topic to department map | `topic` |
| `dim_date` | 675 | calendar day (history + 180 days ahead) | `date` |

## `changes`

| Column | Meaning |
|---|---|
| `id` | Hash of source, title and date |
| `published` | Date the (invented) item was published |
| `source` | Agency: ATO, AUSTRAC (shown as AUS), Law Society (LAW), Fair Work (FWC), DFAT, OAIC |
| `title`, `summary` | Invented text written to resemble an agency bulletin; not a real announcement |
| `link` | Blank for synthetic items |
| `impact` | High / Medium / Low from keyword rules in `classifier.py` |
| `impact_sort` | 1, 2, 3 for sorting High first |
| `action_req` | 1 if the text contains an action phrase and impact is not Low or a deadline exists |
| `deadline` | Earliest explicit future date found in the text, else blank |
| `status` | New / Reviewed / Actioned, set by the generator |
| `data_type` | Always `Sample` |
| `topics`, `audiences` | Comma-joined tags, kept for convenience; the bridge tables are the model |

## Rules and limits

- Tags come from transparent keyword lists in `classifier.py`, not a trained model, so they can miss or over-tag. This is not legal advice.
- Dates are generated relative to the day the generator runs; re-running shifts them slightly against the committed CSVs.
- Department mapping (`dim_topic_department`) is an analyst assumption for a generic law firm.
