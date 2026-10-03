# Tableau Public guide: Regulatory Change Monitor

Tableau Public is free and runs on Mac (download "Tableau Public" desktop app from public.tableau.com).
Everything you publish there is PUBLIC, so only use sample/synthetic or genuinely public data.

## 1. Export the data
```bash
python export_for_bi.py --sample     
```
Files are in `bi_export/`.

## 2. Connect and relate the tables
1. Connect > Text file > `changes.csv`.
2. Drag `change_topics.csv` onto the canvas, relate on `id` = `id`.
3. Drag `change_audiences.csv`, relate on `id` = `id`.
4. Drag `dim_date.csv`, relate `published` = `date`.
Use Relationships (the default "noodle" line), not joins, so counts do not multiply.
Set `published`, `deadline`, `date` to Date type if Tableau reads them as text.

## 3. Calculated fields (Analysis > Create Calculated Field)
```
Changes            COUNTD([id])

Days To Deadline   DATEDIFF('day', TODAY(), [deadline])

Open Action        IF [action_req] = 1 AND [status] <> "Actioned" THEN [id] END
Open Actions       COUNTD([Open Action])

Due In 30 Days     COUNTD(IF [action_req] = 1 AND [status] <> "Actioned"
                        AND [Days To Deadline] >= 0 AND [Days To Deadline] <= 30
                        THEN [id] END)

Overdue            COUNTD(IF [action_req] = 1 AND [status] <> "Actioned"
                        AND [Days To Deadline] < 0 THEN [id] END)

High Impact        COUNTD(IF [impact] = "High" THEN [id] END)
```
Always use COUNTD on `id`: one change can have several topics.

## 4. Sheets
1. **KPIs**: four sheets, each a single number (Changes, High Impact, Open Actions, Due In 30 Days). Format as large text.
2. **Changes by month**: Columns `year_month` (discrete), Rows `Changes`, Color `impact`. Order the colours High red, Medium amber, Low grey; sort impact by `impact_sort`.
3. **By topic**: Rows `topic`, Columns `Changes`, sort descending.
4. **By agency**: Rows `source`, Columns `Changes`, sort descending.
5. **Action tracker**: Rows `title`, `source`, `impact`, `deadline`, `Days To Deadline`, `status`. Filter `action_req` = 1 and `status` not Actioned. Colour `Days To Deadline` (red < 0, amber 0 to 30).
6. **Agency x Topic heatmap**: Rows `source`, Columns `topic`, Mark type Square, Color `Changes`.

## 5. Dashboard
New Dashboard, size Automatic (or 1200 x 800). Top row: four KPI sheets. Middle: monthly chart + topic + agency. Bottom: action tracker, then the heatmap.
Add filters for `source`, `topic`, `audience`, `impact`, `status`; on each filter choose "Apply to Worksheets > All Using This Data Source".
Add a text note: "Sample data. Keyword classification, not legal advice."

## 6. Publish
File > Save to Tableau Public. Use the URL in your CV/LinkedIn/README. Re-export and re-publish after regenerating the data.

## Tips
- Screenshot the dashboard into the repo README as a fallback if the link breaks.
- Be ready to explain the data model: why relationships instead of joins, and why COUNTD.
