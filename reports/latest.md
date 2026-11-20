# Regulatory change report: 20 Nov 2026

Sources checked: 6 (0 ok). **Baseline run:** existing items loaded, nothing flagged as new.


## Source health

| Agency | Feed | Status |
|---|---|---|
| AUSTRAC | Media releases and updates | rss: ReadTimeout: HTTPSConnectionPool(host='www.austrac.gov.au', port=443): Read timed out. (read timeout=12); page: ReadTimeout: HTTPSConnectionPool(host='www.austrac.gov.au', port=443): Read timed out. (read timeout=12); google-news: skipped (robots.txt) |
| ATO | Business and organisations news | rss: HTTPError: 403 Client Error: Forbidden for url: https://www.ato.gov.au/rss.aspx?category=210; page: HTTPError: 403 Client Error: Forbidden for url: https://www.ato.gov.au/businesses-and-organisations/business-bulletins-newsroom; google-news: skipped (robots.txt) |
| Fair Work | Fair Work Ombudsman news | page: ReadTimeout: HTTPSConnectionPool(host='www.fairwork.gov.au', port=443): Read timed out. (read timeout=12); google-news: skipped (robots.txt) |
| OAIC | OAIC news and media | page: HTTPError: 403 Client Error: Forbidden for url: https://www.oaic.gov.au/news/media-centre; google-news: skipped (robots.txt) |
| ASIC | ASIC news | google-news: skipped (robots.txt) |
| Law Society NSW | Law Society news | google-news: skipped (robots.txt) |

_Tags come from keyword rules (`classifier.py`); costs and hours are estimates from the assumptions in `impact_model.py`. Not legal advice._
