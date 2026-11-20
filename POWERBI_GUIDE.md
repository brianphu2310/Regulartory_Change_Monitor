# Power BI guide: Regulatory Change Monitor

> Build notes for the first version of the report. The final .pbix in `powerbi/` extends this with more pages, drill-through, tooltips and header slicers; see the README.

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

## v2: Finance, Time and People pages (impact model)

Run `python impact_model.py` (see [docs/IMPACT_MODEL.md](docs/IMPACT_MODEL.md)), then **Get Data > Text/CSV** for the five new files.

### Relationships

| From (one) | To (many) | Cross-filter |
|---|---|---|
| `changes[id]` | `change_impact[id]` | Single (1:1 in practice) |
| `changes[id]` | `change_effort[id]` | Single |
| `dim_role[role]` | `change_effort[role]` | Single |
| `dim_role[role]` | `capacity_monthly[role]` | Single |
| `dim_date[date]` | `capacity_monthly[month_start]` | Single |

Types: `target_date`, `as_of`, `month_start` = Date; `at_risk` = Whole number; hours and costs = Decimal; costs formatted as currency.
`impact_assumptions` is a reference table with no relationships (shown on the About page so the assumptions are visible).

### Measures

```DAX
One-off Cost        = SUM ( change_impact[total_one_off_cost] )
Internal Cost       = SUM ( change_impact[internal_one_off_cost] )
External Cost       = SUM ( change_impact[external_one_off] )
Ongoing Cost / yr   = SUM ( change_impact[total_ongoing_cost_yr] )
Outstanding Cost    = CALCULATE ( [One-off Cost], change_impact[work_status] = "Outstanding" )
Hours Required      = SUM ( change_effort[one_off_hours] )
Outstanding Hours   = SUM ( change_impact[outstanding_hours] )
At Risk             = SUM ( change_impact[at_risk] )
Avg Lead Time (days)= AVERAGE ( change_impact[lead_time_days] )
Capacity Needed     = SUM ( capacity_monthly[hours_required] )
Capacity Available  = SUM ( capacity_monthly[hours_available] )
Capacity Load %     = DIVIDE ( [Capacity Needed], [Capacity Available] )
Hours Over Capacity = SUM ( capacity_monthly[hours_over_capacity] )
FTE Gap (months)    = DIVIDE ( [Hours Over Capacity], 152 )   -- 152 h = one full-time month (38 h x 4)
```

### Page layout (same Slate & Lime theme and sidebar as v1)

| Page | Top KPI cards | Main visuals | Plain-English takeaway card |
|---|---|---|---|
| **Finance impact** | One-off Cost · Ongoing Cost / yr · Outstanding Cost · External Cost | Cost by topic (bar, internal vs external stacked) · Cost by department (treemap) · Top 10 most expensive changes (table) | "This year's changes cost about $137K once and $23K a year from now on." |
| **Time & deadlines** | Outstanding changes · At Risk · Avg Lead Time | Deadline timeline (scatter: target date × cost, sized by hours, coloured by days left) · Outstanding hours by month due (column) | "27 changes are past their target date; clear them before taking on new work." |
| **People & capacity** | Capacity Load % · Hours Over Capacity · FTE Gap | Hours needed vs available by role (clustered bar with a capacity line) · Load % heatmap (matrix: role × month, conditional colour) | "October needs 400 hours against 140: the Compliance Officer and Principal carry most of it." |

Add a **what-if parameter** `Hourly cost uplift %` (Modeling > New parameter, 0–30%) and use
`Internal Cost x Uplift = [Internal Cost] * ( 1 + 'Hourly cost uplift %'[Value] )` on the Finance page, so a partner can
test a pay rise or contractor rates without touching the data.
