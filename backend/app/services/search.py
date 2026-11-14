"""Robots-permitted public search endpoints used for research, discovery and monitoring.

* Bing News RSS (``/news/search?format=rss`` is allowed by bing.com/robots.txt)
* GDELT DOC 2.0 API (open news index; rate limit one request per ~5s)
* Stack Exchange API (official public API) — real user questions
* Hacker News Algolia API (official public API) — developer/tech discussions
* Federal Register API (US government regulatory documents)
* GOV.UK search Atom feeds (UK government news & guidance)

Google News RSS and anonymous Reddit are intentionally NOT used: both are disallowed for automated
agents by their robots.txt.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlparse

import feedparser

from app.services.fetcher import FetchError, PoliteFetcher, RobotsDisallowed, get_fetcher
from app.services.nlp import clean_text, html_to_text, parse_date, truncate

log = logging.getLogger(__name__)


def _item(title, url, publisher=None, published=None, snippet=None, **extra) -> dict:
    return {
        "title": clean_text(html.unescape(title or "")),
        "url": url,
        "publisher": publisher,
        "published": published,
        "snippet": truncate(html_to_text(snippet or ""), 500) if snippet else None,
        **extra,
    }


def bing_news_url(query: str) -> str:
    return f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss&setlang=en"


def decode_bing_link(link: str) -> str:
    try:
        qs = parse_qs(urlparse(link).query)
        if "url" in qs:
            return qs["url"][0]
    except ValueError:
        pass
    return link


def parse_feed(text: str, source_kind: str = "rss") -> list[dict]:
    feed = feedparser.parse(text)
    items = []
    for e in feed.entries:
        link = e.get("link") or ""
        publisher = None
        if source_kind == "news_search":
            link = decode_bing_link(link)
            publisher = e.get("news_source") or e.get("source", {}).get("title")
        published = parse_date(e.get("published_parsed") or e.get("updated_parsed") or e.get("published") or e.get("updated"))
        snippet = e.get("summary") or e.get("description") or ""
        if not snippet and e.get("content"):
            snippet = e["content"][0].get("value", "")
        items.append(
            _item(
                e.get("title"),
                link,
                publisher=publisher or feed.feed.get("title"),
                published=published,
                snippet=snippet,
                author=e.get("author"),
            )
        )
    return items


def bing_news(query: str, fetcher: PoliteFetcher | None = None) -> list[dict]:
    fetcher = fetcher or get_fetcher()
    try:
        res = fetcher.get(bing_news_url(query))
    except (FetchError, RobotsDisallowed) as exc:
        log.info("bing news failed for %s: %s", query, exc)
        return []
    return [i for i in parse_feed(res.text, "news_search") if i["url"].startswith("http")]


def gdelt_url(query: str, timespan: str = "1month", maxrecords: int = 50) -> str:
    return (
        "https://api.gdeltproject.org/api/v2/doc/doc?query="
        + quote_plus(query + " sourcelang:english")
        + f"&mode=artlist&format=json&maxrecords={maxrecords}&timespan={timespan}&sort=datedesc"
    )


_gdelt_down_until = 0.0


def gdelt(query: str, timespan: str = "1month", fetcher: PoliteFetcher | None = None) -> list[dict]:
    """GDELT fallback with a circuit breaker: after a connection failure it is skipped for 30 minutes."""
    global _gdelt_down_until
    import time

    if time.time() < _gdelt_down_until:
        return []
    fetcher = fetcher or get_fetcher()
    try:
        res = fetcher.get(gdelt_url(query, timespan))
        data = res.json()
    except (FetchError, RobotsDisallowed, ValueError) as exc:
        log.info("gdelt failed for %s: %s", query, exc)
        if isinstance(exc, FetchError) and (exc.status in (None, 429) or "Connect" in str(exc)):
            _gdelt_down_until = time.time() + 1800
        return []
    out = []
    for a in data.get("articles", []):
        published = None
        if a.get("seendate"):
            try:
                published = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                published = None
        out.append(_item(a.get("title"), a.get("url"), publisher=a.get("domain"), published=published, snippet=None))
    return out


def news_search(query: str, fetcher: PoliteFetcher | None = None) -> list[dict]:
    """Bing News first, GDELT as a fallback when Bing returns nothing."""
    items = bing_news(query, fetcher)
    if not items:
        items = gdelt(query, fetcher=fetcher)
    return items


# ------------------------------------------------------------------ Stack Exchange
def stackexchange_url(site: str, query: str) -> str:
    return f"https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=creation&q={quote_plus(query)}&site={site}&pagesize=30&filter=withbody"


def stackexchange(site: str, query: str, fetcher: PoliteFetcher | None = None) -> list[dict]:
    fetcher = fetcher or get_fetcher()
    try:
        data = fetcher.get(stackexchange_url(site, query)).json()
    except (FetchError, RobotsDisallowed, ValueError) as exc:
        log.info("stackexchange failed: %s", exc)
        return []
    out = []
    for q in data.get("items", []):
        published = datetime.fromtimestamp(q["creation_date"], tz=timezone.utc) if q.get("creation_date") else None
        out.append(
            _item(
                q.get("title"),
                q.get("link"),
                publisher=f"{site}.stackexchange.com",
                published=published,
                snippet=q.get("body"),
                score=q.get("score"),
                answer_count=q.get("answer_count"),
                tags=q.get("tags", []),
                item_type="question",
            )
        )
    return out


def stackexchange_sites(fetcher: PoliteFetcher | None = None) -> list[dict]:
    fetcher = fetcher or get_fetcher()
    try:
        data = fetcher.get("https://api.stackexchange.com/2.3/sites?pagesize=400&filter=!SmNnbu6IrvLP5nC(hk").json()
    except (FetchError, RobotsDisallowed, ValueError) as exc:
        log.info("stackexchange sites failed: %s", exc)
        return []
    return [
        {"api_site_parameter": s.get("api_site_parameter"), "name": s.get("name"), "audience": s.get("audience", ""), "site_url": s.get("site_url")}
        for s in data.get("items", [])
        if s.get("site_type") == "main_site"
    ]


# ------------------------------------------------------------------ Hacker News
def hackernews_url(query: str) -> str:
    return f"https://hn.algolia.com/api/v1/search_by_date?query={quote_plus(query)}&tags=(story,comment)&hitsPerPage=30"


def hackernews(query: str, fetcher: PoliteFetcher | None = None) -> list[dict]:
    fetcher = fetcher or get_fetcher()
    try:
        data = fetcher.get(hackernews_url(query)).json()
    except (FetchError, RobotsDisallowed, ValueError) as exc:
        log.info("hn failed: %s", exc)
        return []
    out = []
    for h in data.get("hits", []):
        title = h.get("title") or h.get("story_title") or ""
        text = h.get("comment_text") or h.get("story_text") or ""
        url = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        out.append(
            _item(
                title if not h.get("comment_text") else f"Comment on: {title}",
                url,
                publisher="Hacker News",
                published=parse_date(h.get("created_at")),
                snippet=text or title,
                author=h.get("author"),
                item_type="post",
            )
        )
    return out


# ------------------------------------------------------------------ Government sources
def federal_register_url(term: str) -> str:
    return f"https://www.federalregister.gov/api/v1/documents.rss?conditions%5Bterm%5D={quote_plus(term)}&order=newest"


def govuk_url(keywords: str) -> str:
    return f"https://www.gov.uk/search/news-and-communications.atom?keywords={quote_plus(keywords)}&order=updated-newest"


def discover_feed_links(html_text: str, base_url: str) -> list[str]:
    """Return RSS/Atom feed URLs advertised by an HTML page via <link rel="alternate">."""
    from urllib.parse import urljoin

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text or "", "lxml")
    feeds = []
    for link in soup.find_all("link", rel=lambda r: r and "alternate" in r):
        t = (link.get("type") or "").lower()
        if "rss" in t or "atom" in t:
            href = link.get("href")
            if href and "comments" not in href:
                feeds.append(urljoin(base_url, href))
    return feeds
