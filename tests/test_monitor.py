"""Offline tests for the live monitor: parsing, robots handling, de-duplication and the run end to end."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from monitor import fetch as F
from monitor import run as R
from monitor.sources import Source

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>AUSTRAC guidance: law firms must enrol by 31 March 2027</title>
<link>https://www.austrac.gov.au/news-and-media/media-release/tranche-2-enrolment</link>
<pubDate>Wed, 18 Nov 2026 09:00:00 +1100</pubDate>
<description>Legal practitioners must enrol as reporting entities. Penalties apply for breach.</description></item>
<item><title>Office closed over the holiday period</title>
<link>https://www.austrac.gov.au/news-and-media/media-release/holiday-closure</link>
<pubDate>Tue, 17 Nov 2026 09:00:00 +1100</pubDate><description>Speeches.</description></item>
</channel></rss>"""

PAGE = """<html><body><ul>
<li><a href="/newsroom/news/minimum-wage-increase-for-award-employees">Minimum wage increase for award employees from 1 July</a>
<span>12 November 2026</span> Employers must update payroll.</li>
<li><a href="/newsroom/news">All news</a></li>
<li><a href="/about-us">About us and our role in the workplace</a></li>
</ul></body></html>"""


class Resp:
    def __init__(self, body):
        self.content = body if isinstance(body, bytes) else body.encode()
        self.text = self.content.decode()


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(F, "allowed", lambda url: True)
    monkeypatch.setattr(F, "_get", lambda url: Resp(RSS if url.endswith(".xml") else PAGE))


def test_rss_items_are_parsed_with_dates(offline):
    items = F.from_rss(Source("AUSTRAC", "x", rss="https://a/rss.xml", page=None))
    assert len(items) == 2 and items[0]["published"] == date(2026, 11, 18)


def test_page_keeps_only_article_links_and_finds_dates(offline):
    src = Source("Fair Work", "x", rss=None, page="https://www.fairwork.gov.au/newsroom/news", link_pattern=r"/newsroom/news/[^?#]+")
    items = F.from_page(src)
    assert [i["title"] for i in items] == ["Minimum wage increase for award employees from 1 July"]
    assert items[0]["published"] == date(2026, 11, 12)


def test_robots_block_is_reported_not_bypassed(monkeypatch):
    monkeypatch.setattr(F, "allowed", lambda url: False)
    items, status = F.fetch(Source("X", "x", rss="https://a/rss.xml", page="https://a/news"))
    assert items == [] and "robots.txt" in status


def test_a_failing_source_does_not_raise(monkeypatch):
    monkeypatch.setattr(F, "allowed", lambda url: True)
    def boom(url):
        raise ConnectionError("down")
    monkeypatch.setattr(F, "_get", boom)
    items, status = F.fetch(Source("X", "x", rss="https://a/rss.xml", page=None))
    assert items == [] and "ConnectionError" in status


def test_same_link_gets_same_id():
    assert F.item_id("https://a.gov.au/x/") == F.item_id("https://A.gov.au/x")


def test_run_flags_only_new_relevant_changes(offline, monkeypatch, tmp_path):
    monkeypatch.setattr(R, "LIVE", tmp_path / "live")
    monkeypatch.setattr(R, "REPORT", tmp_path / "reports" / "latest.md")
    monkeypatch.setattr(R, "SOURCES", [Source("AUSTRAC", "Media", rss="https://a/rss.xml", page=None)])
    monkeypatch.setattr(R, "today_sydney", lambda: date(2026, 11, 20))

    R.main()  # first run is the baseline: loads, flags nothing
    assert "Baseline run" in R.REPORT.read_text()
    changes = pd.read_csv(R.LIVE / "changes.csv")
    assert len(changes) == 1 and changes.loc[0, "impact"] == "High"   # the conference item is not relevant

    R.main()  # nothing new the second time
    assert len(pd.read_csv(R.LIVE / "changes.csv")) == 1
    assert "New relevant changes: **0**" in R.REPORT.read_text()
    assert (R.LIVE / "change_impact.csv").exists() and len(pd.read_csv(R.LIVE / "run_log.csv")) == 2
    # the v1 report's tables are written too, with the same columns as the sample data
    for f in ("changes.csv", "change_topics.csv", "change_audiences.csv", "dim_date.csv", "dashboard_changes.csv"):
        sample = set(pd.read_csv(Path(__file__).resolve().parent.parent / "bi_export" / f, nrows=1).columns)
        assert sample <= set(pd.read_csv(R.LIVE / f, nrows=1).columns), f
