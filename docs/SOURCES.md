# Sources: what was tried, what works where

35 candidate feeds, APIs and news pages from federal regulators, NSW agencies and legal-profession bodies were
probed from a GitHub Actions runner on 21 Nov 2026 with [`monitor/probe.py`](../monitor/probe.py). Every one allowed
our user agent in robots.txt; the differences are whether the site answers cloud traffic and whether the page can be
read without JavaScript. Re-run the probe any time: `python -m monitor.probe`.

## In the monitor (15 sources)

| Source | Method | From the cloud | Items on 21 Nov 2026 |
|---|---|---|---|
| Treasury: open consultations | News page | Works | 10 |
| Attorney-General's consultation hub | News page | Works | 8 |
| APRA: news and publications | News page | Works | 11 |
| Federal Register of Legislation | Public OData API (`api.prod.legislation.gov.au/v1/Titles`) | Works | 200 newest Acts and instruments |
| Law Society of NSW: news and media releases | News page | Works | 25 |
| Legal Services Board + Commissioner (Uniform Law) | News page | Works | 10 |
| Revenue NSW: news and media releases | News page | Works | 20 |
| NSW Fair Trading: news | News page | Works | 9 |
| NSW Government: ministerial releases | News page | Works | 10 |
| NSW Communities and Justice: media releases | News page | Works | 10 |
| SafeWork NSW: media releases | News page | Works | 8 |
| AUSTRAC: news and media releases | News page | Time-out | Desktop run only |
| ATO: all new information | RSS (`/rss/all-new-information.xml`) | 403 | Desktop run only |
| Fair Work Ombudsman: news | News page | Time-out | Desktop run only |
| OAIC: media centre | News page | 403 | Desktop run only |

First full cloud run: 321 items fetched, **29 relevant** to a law firm kept (Revenue NSW 15, Treasury 5, Federal
Register 4, NSW Fair Trading 3, APRA 1, Attorney-General's 1), 7 needing action.

## Tried and left out

| Source | Why |
|---|---|
| Fair Work Commission, ARNECC (e-conveyancing rules), NSW legislation feeds and export, NSW Parliament bills | 403 from the cloud |
| ag.gov.au news, DFAT sanctions pages, IPC NSW | Time-out from the cloud |
| ASIC, ACCC media releases | The list is built by JavaScript; the page has no items |
| NSW Government Gazette | PDFs only; titles say nothing about the content |
| Law Society Journal feed and WordPress API | Valid but empty |
| Registrar General NSW news | Page answered, but no article links matched |
| Google News search feeds | robots.txt disallows them |

## How relevance is decided

Every item goes through `classifier.py`. Keywords match whole words only (so "entitlement" no longer counts as
"title"), and government notices that share keywords but do not bind a firm (veterans' and family payments,
parliamentary super, Medicare, data-matching notices, ASIC class orders) are excluded. Reviewing the first run removed
13 false positives this way. Items with no topic are recorded in `seen.csv` and `fetched_latest.csv` but not reported.
