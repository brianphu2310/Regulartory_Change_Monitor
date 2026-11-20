"""Polite fetching: robots.txt check, identifying user agent, timeouts, one request per page."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from .sources import Source

UA = "RegulatoryChangeMonitor/1.0 (portfolio project; +https://github.com/brianphu2310/Regulartory_Change_Monitor)"
TIMEOUT = 12
_DATE = re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(20\d{2})\b", re.I)
_robots: dict[str, robotparser.RobotFileParser] = {}


def item_id(link: str) -> str:
    return hashlib.sha1(link.strip().rstrip("/").lower().encode()).hexdigest()[:16]


def allowed(url: str) -> bool:
    base = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if base not in _robots:
        rp = robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=TIMEOUT)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch(UA, url)


def _get(url: str) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-AU"}, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def parse_date(text: str) -> date | None:
    m = _DATE.search(text or "")
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)[:3]} {m.group(3)}", "%d %b %Y").date()
    except ValueError:
        return None


def from_rss(src: Source) -> list[dict]:
    feed = feedparser.parse(_get(src.rss).content)
    if not feed.entries:
        raise ValueError("feed has no entries")
    out = []
    for e in feed.entries:
        published = None
        for key in ("published", "updated"):
            if e.get(key):
                try:
                    published = parsedate_to_datetime(e[key]).date()
                except (TypeError, ValueError):
                    published = parse_date(e[key])
                break
        summary = BeautifulSoup(e.get("summary", ""), "html.parser").get_text(" ", strip=True)
        title = e.get("title", "").strip()
        out.append({"title": title, "summary": summary[:600], "link": e.get("link", ""),
                    "published": published})
    return out


def from_page(src: Source) -> list[dict]:
    soup = BeautifulSoup(_get(src.page).text, "html.parser")
    pat, seen, out = re.compile(src.link_pattern), set(), []
    for a in soup.find_all("a", href=True):
        link = urljoin(src.page, a["href"]).split("#")[0]
        title = a.get_text(" ", strip=True)
        if not pat.search(urlparse(link).path) or link.rstrip("/") == src.page.rstrip("/") or len(title) < 15 or link in seen:
            continue
        seen.add(link)
        block = a.find_parent(["article", "li", "div"]) or a
        text = block.get_text(" ", strip=True)
        out.append({"title": title, "summary": text.replace(title, "", 1).strip()[:600], "link": link,
                    "published": parse_date(text)})
    if not out:
        raise ValueError("no article links matched")
    return out


def fetch(src: Source) -> tuple[list[dict], str]:
    """Return (items, status). Never raises: a failing source is reported, not fatal."""
    errors = []
    for kind, url, fn in (("rss", src.rss, from_rss), ("page", src.page, from_page)):
        if not url:
            continue
        if not allowed(url):
            errors.append(f"{kind}: skipped (robots.txt)")
            continue
        try:
            items = fn(src)
            for it in items:
                it.update(source=src.agency, feed=src.name, via=kind)
            return items, f"ok via {kind} ({len(items)} items)"
        except Exception as e:  # noqa: BLE001 - one bad source must not stop the run
            errors.append(f"{kind}: {type(e).__name__}: {str(e)[:120]}")
    return [], "; ".join(errors) or "no url configured"
