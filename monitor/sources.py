"""Public pages the monitor watches.

Each source tries, in order: the agency's RSS feed, its news listing page, then a Google News RSS search limited to
the agency's own domain. The fallback exists because several agency sites refuse cloud runners: from GitHub Actions
the ATO and OAIC answer 403 and AUSTRAC and Fair Work time out, while the same pages open normally from a desktop.

Only official, public pages are used. The fetcher checks robots.txt before every request and skips a source it is
not allowed to read, so a blocked source shows up as "skipped (robots.txt)" in the run log instead of being worked around.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    agency: str
    name: str
    rss: str | None            # RSS / Atom feed, tried first
    page: str | None           # news listing page
    link_pattern: str = ""     # regex an article link on `page` must match
    site: str = ""             # domain for the Google News fallback

    @property
    def gnews(self) -> str | None:
        if not self.site:
            return None
        return f"https://news.google.com/rss/search?q=site:{self.site}+when:14d&hl=en-AU&gl=AU&ceid=AU:en"


SOURCES = [
    Source("AUSTRAC", "Media releases and updates",
           rss="https://www.austrac.gov.au/media-release/rss.xml",
           page="https://www.austrac.gov.au/news-and-media/news-and-media-releases",
           link_pattern=r"/(news-and-media/media-release|news-and-media/news|business/updates|about-us/media-release)/[^/?#]+",
           site="austrac.gov.au"),
    Source("ATO", "Business and organisations news",
           rss="https://www.ato.gov.au/rss.aspx?category=210",
           page="https://www.ato.gov.au/businesses-and-organisations/business-bulletins-newsroom",
           link_pattern=r"/businesses-and-organisations/business-bulletins-newsroom/[^?#]+",
           site="ato.gov.au"),
    Source("Fair Work", "Fair Work Ombudsman news",
           rss=None,
           page="https://www.fairwork.gov.au/newsroom/news",
           link_pattern=r"/newsroom/news/[^?#]+",
           site="fairwork.gov.au"),
    Source("OAIC", "OAIC news and media",
           rss=None,
           page="https://www.oaic.gov.au/news/media-centre",
           link_pattern=r"/news/media-centre/[^?#]+",
           site="oaic.gov.au"),
    Source("ASIC", "ASIC news", rss=None, page=None, site="asic.gov.au"),
    Source("Law Society NSW", "Law Society news", rss=None, page=None, site="lawsociety.com.au"),
]
