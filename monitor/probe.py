"""Check candidate sources from wherever this runs: robots.txt, HTTP status, and what can be parsed.

    python -m monitor.probe            # prints one line per candidate, writes probe_results.csv

Used to decide which sources go into sources.py: run it from GitHub Actions to see what the cloud can reach.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from urllib.parse import urljoin, urlparse

import feedparser
import pandas as pd
import requests
from bs4 import BeautifulSoup

from .fetch import TIMEOUT, UA, allowed

LAST_WEEK = (date.today() - timedelta(days=14)).isoformat()
# (agency, kind, url, link regex for pages)
CANDIDATES = [
    ("ATO", "rss", "https://www.ato.gov.au/rss/all-new-information.xml", ""),
    ("ATO", "rss", "https://www.ato.gov.au/rss/media-centre.xml", ""),
    ("ATO", "rss", "https://www.ato.gov.au/rss/businesses-and-organisations.xml", ""),
    ("ATO", "rss", "https://www.ato.gov.au/rss/super-for-employers.xml", ""),
    ("ATO", "rss", "https://www.ato.gov.au/rss/tax-professionals.xml", ""),
    ("AUSTRAC", "page", "https://www.austrac.gov.au/news-and-media/news-and-media-releases", r"/news-and-media/(article|media-release)/"),
    ("Fair Work Ombudsman", "page", "https://www.fairwork.gov.au/newsroom/news", r"/newsroom/news/."),
    ("Fair Work Commission", "page", "https://www.fwc.gov.au/about-us/news-and-media/news", r"/news-and-media/news/."),
    ("OAIC", "page", "https://www.oaic.gov.au/news/media-centre", r"/news/media-centre/."),
    ("APRA", "page", "https://www.apra.gov.au/news-and-publications", r"/news-and-publications/."),
    ("ASIC", "page", "https://asic.gov.au/newsroom/media-releases/", r"/newsroom/media-releases/."),
    ("Treasury", "page", "https://treasury.gov.au/consultation", r"^/consultation/c20\d{2}-\d+$"),
    ("Attorney-General's", "page", "https://consultations.ag.gov.au/", r"^/[a-z-]+/[a-z0-9-]+/?$"),
    ("Attorney-General's", "page", "https://www.ag.gov.au/about-us/news-and-media", r"/news-and-media/."),
    ("DFAT Sanctions", "page", "https://www.dfat.gov.au/international-relations/security/sanctions", r"/sanctions/."),
    ("Federal Register", "api", f"https://api.prod.legislation.gov.au/v1/Titles?$filter=asMadeRegisteredAt ge {LAST_WEEK}T00:00:00Z&$top=50&$select=id,name,collection,asMadeRegisteredAt", ""),
    ("Federal Register", "api", f"https://api.prod.legislation.gov.au/v1/Titles?$top=5&$orderby=asMadeRegisteredAt desc&$select=id,name,collection,asMadeRegisteredAt", ""),
    ("NSW Legislation", "rss", "https://legislation.nsw.gov.au/feed?id=newmadelegislation", ""),
    ("NSW Legislation", "api", "https://legislation.nsw.gov.au/export/week?format=json", ""),
    ("NSW Gazette", "page", "https://gazette.nsw.gov.au/", r"/gazette/20\d{2}/"),
    ("NSW Parliament", "page", "https://www.parliament.nsw.gov.au/bills/Pages/current-bills.aspx", r"bill-details|bills/Pages/"),
    ("Law Society NSW", "page", "https://www.lawsociety.com.au/resources/news-and-media", r"/news-media-releases/."),
    ("Law Society NSW", "rss", "https://www.lawsociety.com.au/rss.xml", ""),
    ("LSJ", "rss", "https://lsj.com.au/feed/", ""),
    ("LSJ", "api", "https://lsj.com.au/wp-json/wp/v2/posts?per_page=10&_fields=date,link,title", ""),
    ("Revenue NSW", "page", "https://www.revenue.nsw.gov.au/news-media-releases", r"/news-media-releases/."),
    ("Registrar General NSW", "page", "https://www.registrargeneral.nsw.gov.au/news", r"/news/."),
    ("NSW Fair Trading", "page", "https://www.nsw.gov.au/departments-and-agencies/fair-trading/news", r"/(fair-trading/news|ministerial-releases)/."),
    ("NSW Government", "page", "https://www.nsw.gov.au/ministerial-releases", r"/ministerial-releases/."),
    ("NSW DCJ", "page", "https://dcj.nsw.gov.au/news-and-media/media-releases/2026.html", r"/media-releases/20\d{2}/."),
    ("SafeWork NSW", "page", "https://www.safework.nsw.gov.au/news", r"/news/safework-media-releases/."),
    ("IPC NSW", "page", "https://www.ipc.nsw.gov.au/news-events/media-releases", r"/news-events/media-releases/."),
    ("ARNECC", "rss", "https://www.arnecc.gov.au/feed/", ""),
    ("ARNECC", "api", "https://www.arnecc.gov.au/wp-json/wp/v2/posts?per_page=10&_fields=date,link,title", ""),
    ("Legal Services Board VIC", "page", "https://lsbc.vic.gov.au/news-updates/news", r"/news-updates/news/."),
]


def probe_one(agency: str, kind: str, url: str, pattern: str) -> dict:
    row = {"agency": agency, "kind": kind, "url": url, "robots": "", "status": "", "items": 0, "latest": "", "sample": ""}
    try:
        if not allowed(url):
            row["robots"] = "disallowed"
            return row
        row["robots"] = "allowed"
        headers = {"User-Agent": UA, "Accept": "application/json" if kind == "api" else "*/*"}
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        row["status"] = r.status_code
        if r.status_code != 200:
            return row
        if kind == "rss":
            f = feedparser.parse(r.content)
            row["items"] = len(f.entries)
            if f.entries:
                row["latest"] = f.entries[0].get("published", f.entries[0].get("updated", ""))[:25]
                row["sample"] = f.entries[0].get("title", "")[:70]
        elif kind == "api":
            data = r.json()
            items = data.get("value", data) if isinstance(data, dict) else data
            if isinstance(items, dict):
                items = items.get("items") or items.get("results") or list(items.values())
            row["items"] = len(items) if isinstance(items, list) else 1
            if isinstance(items, list) and items:
                first = items[0]
                row["sample"] = str(first.get("name") or first.get("title") or first)[:70] if isinstance(first, dict) else str(first)[:70]
                row["latest"] = str(first.get("asMadeRegisteredAt") or first.get("date") or "")[:25] if isinstance(first, dict) else ""
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            rx = re.compile(pattern)
            links = {urljoin(url, a["href"]) for a in soup.find_all("a", href=True)
                     if rx.search(urlparse(urljoin(url, a["href"])).path) and len(a.get_text(strip=True)) >= 15}
            row["items"] = len(links)
            row["sample"] = next(iter(sorted(links)), "")[:70]
    except Exception as e:  # noqa: BLE001
        row["status"] = f"{type(e).__name__}: {str(e)[:60]}"
    return row


def main() -> int:
    rows = [probe_one(*c) for c in CANDIDATES]
    df = pd.DataFrame(rows)
    df.to_csv("probe_results.csv", index=False)
    for r in rows:
        print(f"{r['agency'][:22]:<22} {r['kind']:<4} {r['robots']:<10} {str(r['status'])[:40]:<40} items={r['items']:<4} "
              f"latest={r['latest'][:16]:<16} {r['sample'][:60]}  <{r['url'][:90]}>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
