# Power BI guide: Regulatory Change Monitor

## 1. Export the data
```bash
python export_for_bi.py --sample     # regenerate the synthetic dataset and export
```
Creates `bi_export/` with `changes.csv`, `change_topics.csv`, `change_audiences.csv`, `dim_date.csv`.
Re-run the export after regenerating data, then click **Refresh** in Power BI.

> Power BI Desktop runs on Windows only. On a Mac use a Windows PC/VM, or the Power BI web
> service (app.powerbi.com), or Tableau Public (same CSVs work). Web editing has some
> modelling limits, so build and test the measures in Desktop if you can.

## 2. Load and model
Get Data > Text/CSV: load all four files. In Power Query set types:
`published`, `deadline`, `date`, `month_start`, `week_start` = Date; `action_req`, `impact_sort` = Whole number.

Relationships (Model view):
| From (one) | To (many) | Cross-filter |
|---|---|---|
| `dim_date[date]` | `changes[published]` | Single |
| `changes[id]` | `change_topics[id]` | **Both** (so a Topic slicer filters changes) |
| `changes[id]` | `change_audiences[id]` | **Both** |

Mark `dim_date` as a date table. Set `changes[impact]` Sort by column = `impact_sort`.
Set `dim_date[month_name]` Sort by column = `month_num`.

## 3. DAX
Calculated column on `changes`:
```DAX
Days To Deadline =
IF ( ISBLANK ( changes[deadline] ), BLANK (), DATEDIFF ( TODAY (), changes[deadline], DAY ) )
```
Measures (create a table `_Measures`):
```DAX
Total Changes = COUNTROWS ( changes )

High Impact = CALCULATE ( [Total Changes], changes[impact] = "High" )

Open Actions =
CALCULATE ( [Total Changes], changes[action_req] = 1, changes[status] <> "Actioned" )

Due In 30 Days =
CALCULATE ( [Open Actions], changes[deadline] >= TODAY (), changes[deadline] <= TODAY () + 30 )

Overdue Actions =
CALCULATE ( [Open Actions], changes[deadline] < TODAY () )

Action Rate = DIVIDE ( [Open Actions], [Total Changes] )

Changes Last 30 Days =
CALCULATE ( [Total Changes], DATESINPERIOD ( dim_date[date], TODAY (), -30, DAY ) )

Deadline Status =
SWITCH (
    TRUE (),
    ISBLANK ( SELECTEDVALUE ( changes[deadline] ) ), "No fixed date",
    SELECTEDVALUE ( changes[Days To Deadline] ) < 0, "Overdue",
    SELECTEDVALUE ( changes[Days To Deadline] ) <= 30, "Due soon",
    "Later"
)
```

## 4. Report pages
**Page 1: Overview**
- Cards: Total Changes, High Impact, Open Actions, Due In 30 Days.
- Stacked column: X = `dim_date[year_month]`, Y = Total Changes, Legend = `changes[impact]`.
  Colours: High red, Medium amber, Low grey.
- Bar: `change_topics[topic]` by Total Changes. Bar: `changes[source]` by Total Changes.
- Slicers: Agency, Topic, Audience, Impact.

**Page 2: Action tracker**
- Table: title, source, impact, deadline, Days To Deadline, status. Filter `action_req = 1`.
- Conditional formatting on Days To Deadline: red < 0, amber 0 to 30.
- Slicer: status.

**Page 3: Agency x Topic**
- Matrix: Rows = `changes[source]`, Columns = `change_topics[topic]`, Values = Total Changes, with a colour scale (heatmap).

Add a text box on every page: "Sample data. Keyword classification, not legal advice." (the data is synthetic).

## 5. Publishing for your portfolio
Screenshots of each page in the repo README are enough. Publish-to-web exposes data publicly, so only do it with synthetic or genuinely public data.
