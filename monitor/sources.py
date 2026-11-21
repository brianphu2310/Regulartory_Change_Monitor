"""Public pages the monitor watches.

Each source tries its RSS feed first, then its news listing page. Only official, public pages are used. The fetcher
checks robots.txt before every request and skips a source it is not allowed to read, so a blocked source shows up as
"skipped (robots.txt)" in the run log instead of being worked around.

Where it runs matters: many government sites refuse data-centre traffic (403 or time-out), so the scheduled cloud run
covers the sources marked "cloud OK" below and `run_local.ps1` (same image, desktop network) covers the rest.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    agency: str
    name: str
    rss: str | None            # RSS / Atom feed, tried first
    page: str | None           # news listing page
    link_pattern: str = ""     # regex an article link on `page` must match
    api: str | None = None     # JSON API (Federal Register of Legislation), tried after the feed


# Tested from a GitHub runner on 21 Nov 2026 with `python -m monitor.probe`:
#   cloud OK  Treasury, Attorney-General's consultations, APRA, Federal Register API, Law Society NSW, Revenue NSW,
#             NSW Fair Trading, NSW ministerial releases, NSW DCJ, SafeWork NSW, Legal Services Board (VIC)
#   blocked   ATO, OAIC, Fair Work Commission, ARNECC, NSW legislation, NSW Parliament (403);
#             AUSTRAC, Fair Work Ombudsman, ag.gov.au, DFAT, IPC NSW (time-out)
#   no use    ASIC and ACCC (JavaScript-only lists), NSW Gazette (PDFs only), LSJ feed (empty)
SOURCES = [
    # federal regulators
    Source("AUSTRAC", "Media releases and updates", rss=None,
           page="https://www.austrac.gov.au/news-and-media/news-and-media-releases",
           link_pattern=r"/news-and-media/(article|media-release)/[^/?#]+"),
    Source("ATO", "New information (all topics)", rss="https://www.ato.gov.au/rss/all-new-information.xml", page=None),
    Source("Fair Work", "Fair Work Ombudsman news", rss=None,
           page="https://www.fairwork.gov.au/newsroom/news", link_pattern=r"/newsroom/news/[^?#]+"),
    Source("OAIC", "OAIC news and media", rss=None,
           page="https://www.oaic.gov.au/news/media-centre", link_pattern=r"/news/media-centre/[^?#]+"),
    Source("APRA", "News and publications", rss=None,
           page="https://www.apra.gov.au/news-and-publications", link_pattern=r"^/news-and-publications/[a-z0-9-]{12,}$"),
    Source("Treasury", "Open consultations", rss=None,
           page="https://treasury.gov.au/consultation", link_pattern=r"^/consultation/c20\d{2}-\d+$"),
    Source("Attorney-General's", "Consultation hub", rss=None,
           page="https://consultations.ag.gov.au/", link_pattern=r"^/[a-z-]+/[a-z0-9-]+/?$"),
    Source("Federal Register", "New Acts and instruments", rss=None, page=None,
           api="https://api.prod.legislation.gov.au/v1/Titles?$top=200&$orderby=asMadeRegisteredAt%20desc"
               "&$select=id,name,collection,asMadeRegisteredAt"),
    # NSW and the legal profession
    Source("Law Society NSW", "News and media releases", rss=None,
           page="https://www.lawsociety.com.au/resources/news-and-media",
           link_pattern=r"/publications-and-resources/news-media-releases/[^?#]+"),
    Source("Legal Services Board", "Uniform Law Commissioner news (VIC)", rss=None,
           page="https://lsbc.vic.gov.au/news-updates/news", link_pattern=r"/news-updates/news/[^?#]+"),
    Source("Revenue NSW", "News and media releases", rss=None,
           page="https://www.revenue.nsw.gov.au/news-media-releases", link_pattern=r"/news-media-releases/[^?#]+"),
    Source("NSW Fair Trading", "Fair Trading news", rss=None,
           page="https://www.nsw.gov.au/departments-and-agencies/fair-trading/news",
           link_pattern=r"/(fair-trading/news|ministerial-releases)/[^?#]+"),
    Source("NSW Government", "Ministerial releases", rss=None,
           page="https://www.nsw.gov.au/ministerial-releases", link_pattern=r"^/ministerial-releases/[^?#]+"),
    Source("NSW DCJ", "Justice media releases", rss=None,
           page="https://dcj.nsw.gov.au/news-and-media/media-releases/2026.html",
           link_pattern=r"/news-and-media/media-releases/20\d{2}/[^?#]+"),
    Source("SafeWork NSW", "SafeWork media releases", rss=None,
           page="https://www.safework.nsw.gov.au/news", link_pattern=r"/news/safework-media-releases/[^?#]+"),
]
