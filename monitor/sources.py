"""Public pages the monitor watches. Each source tries its RSS feed first and falls back to the news listing page.

Only official, public agency pages are used. The fetcher checks each site's robots.txt before every request and
skips a source it is not allowed to read, so a blocked source shows up as "skipped (robots.txt)" in the run log
instead of being worked around.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    agency: str
    name: str
    rss: str | None            # RSS / Atom feed, tried first
    page: str | None           # news listing page, used when there is no feed or it fails
    link_pattern: str = ""     # regex an article link on `page` must match


SOURCES = [
    Source("AUSTRAC", "Media releases and updates",
           rss="https://www.austrac.gov.au/media-release/rss.xml",
           page="https://www.austrac.gov.au/news-and-media/news-and-media-releases",
           link_pattern=r"/(news-and-media/media-release|news-and-media/news|business/updates|about-us/media-release)/[^/?#]+"),
    Source("ATO", "Business and organisations news",
           rss="https://www.ato.gov.au/rss.aspx?category=210",
           page="https://www.ato.gov.au/businesses-and-organisations/business-bulletins-newsroom",
           link_pattern=r"/businesses-and-organisations/business-bulletins-newsroom/[^?#]+"),
    Source("ATO", "Media releases",
           rss="https://www.ato.gov.au/rss.aspx?category=196",
           page="https://www.ato.gov.au/media-centre",
           link_pattern=r"/media-centre/[^?#]+"),
    Source("Fair Work", "Fair Work Ombudsman news",
           rss=None,
           page="https://www.fairwork.gov.au/newsroom/news",
           link_pattern=r"/newsroom/news/[^?#]+"),
    Source("OAIC", "OAIC news and media",
           rss=None,
           page="https://www.oaic.gov.au/news/media-centre",
           link_pattern=r"/news/media-centre/[^?#]+"),
]
