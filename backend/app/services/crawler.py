"""Monitoring engine: fetch approved sources, normalise items, detect new/changed content, deduplicate,
preserve history, then hand new evidence to the analysis engine.

A failing source never aborts a run: each source is processed inside its own try/except and its
health is updated (healthy → degraded → failing → dead).
"""
from __future__ import annotations

import difflib
import logging
import re
import time
from datetime import timedelta

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Company, CrawlLog, CrawlRun, RawItem, Source, utcnow
from app.services import nlp
from app.services.fetcher import FetchError, PoliteFetcher, RobotsDisallowed, get_fetcher
from app.services.search import decode_bing_link, parse_feed

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- source handlers
def _items_from_feed(src: Source, text: str) -> list[dict]:
    kind = "news_search" if src.source_type == "news_search" else "rss"
    items = parse_feed(text, kind)
    for it in items:
        it["item_type"] = "filing" if src.source_type in ("federal_register", "govuk") else "article"
        if src.source_type in ("federal_register", "govuk"):
            it["publisher"] = "US Federal Register" if src.source_type == "federal_register" else "GOV.UK"
        if not it.get("publisher"):
            it["publisher"] = nlp.domain_of(src.url)
        it["url"] = decode_bing_link(it["url"])
    must = (src.config or {}).get("must_mention")
    if must:
        key = nlp.name_key(must)
        items = [i for i in items if key in nlp.name_key(i["title"] + " " + (i.get("snippet") or ""))]
    return items


def _items_from_stackexchange(src: Source, data: dict) -> list[dict]:
    from datetime import datetime, timezone

    out = []
    site = (src.config or {}).get("site", "stackexchange")
    for q in data.get("items", []):
        body = nlp.html_to_text(q.get("body", ""))
        out.append({
            "title": nlp.clean_text(q.get("title", "")).replace("&#39;", "'").replace("&quot;", '"'),
            "url": q.get("link"),
            "snippet": nlp.truncate(body, 500),
            "content": body[:5000],
            "published": datetime.fromtimestamp(q["creation_date"], tz=timezone.utc) if q.get("creation_date") else None,
            "publisher": f"{site} (Stack Exchange)",
            "author": (q.get("owner") or {}).get("display_name"),
            "item_type": "question",
            "extra": {"score": q.get("score"), "answers": q.get("answer_count"), "tags": q.get("tags", [])},
        })
    return out


def _items_from_hn(data: dict) -> list[dict]:
    out = []
    for h in data.get("hits", []):
        title = h.get("title") or h.get("story_title") or ""
        text = nlp.html_to_text(h.get("comment_text") or h.get("story_text") or "")
        out.append({
            "title": title if not h.get("comment_text") else f"Comment on: {title}",
            "url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "snippet": nlp.truncate(text or title, 500),
            "content": text[:5000],
            "published": nlp.parse_date(h.get("created_at")),
            "publisher": "Hacker News",
            "author": h.get("author"),
            "item_type": "post",
            "extra": {"points": h.get("points")},
        })
    return out


def _main_text(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [nlp.clean_text(x) for x in text.split("\n")]
    out, seen = [], set()
    for ln in lines:
        if len(ln) < 25 or ln in seen:
            continue
        seen.add(ln)
        out.append(ln)
    return out


def _page_change(src: Source, html: str) -> tuple[list[dict], str]:
    lines = _main_text(html)
    norm = "\n".join(lines)
    new_hash = nlp.sha256(norm)
    soup = BeautifulSoup(html, "lxml")
    published, date_src = nlp.extract_html_date(soup)
    if src.content_hash is None:
        item = {
            "title": f"Baseline snapshot: {src.name}",
            "url": src.url,
            "snippet": nlp.truncate(" ".join(lines[:6]), 400),
            "content": norm[:20000],
            "published": published,
            "publisher": nlp.domain_of(src.url),
            "item_type": "page_snapshot",
            "date_source": date_src,
        }
        return [item], new_hash
    if new_hash == src.content_hash:
        return [], new_hash
    prev = (src.config or {}).get("last_lines", [])
    added = [ln for ln in lines if ln not in set(prev)]
    removed = [ln for ln in prev if ln not in set(lines)]
    if not added and not removed:
        return [], new_hash
    sm = difflib.SequenceMatcher(None, "\n".join(prev), norm)
    changed_ratio = 1 - sm.quick_ratio()
    item = {
        "title": f"{src.name.replace(' (change monitor)', '')}: page content changed ({len(added)} added / {len(removed)} removed lines)",
        "url": src.url,
        "snippet": nlp.truncate("Added: " + " | ".join(added[:5]), 500) if added else nlp.truncate("Removed: " + " | ".join(removed[:5]), 500),
        "content": "ADDED:\n" + "\n".join(added[:60]) + "\n\nREMOVED:\n" + "\n".join(removed[:60]),
        "published": None,
        "publisher": nlp.domain_of(src.url),
        "item_type": "page_change",
        "date_source": "detected",
        "extra": {"added": added[:30], "removed": removed[:30], "change_ratio": round(changed_ratio, 3)},
    }
    return [item], new_hash


_reddit_token: dict = {}


def _reddit_items(src: Source, fetcher: PoliteFetcher) -> list[dict]:
    s = get_settings()
    if not (s.reddit_client_id and s.reddit_client_secret):
        raise FetchError("Reddit requires REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET (official API); anonymous crawling is disallowed by robots.txt")
    now = time.time()
    if not _reddit_token or _reddit_token.get("exp", 0) < now:
        r = httpx.post("https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"}, auth=(s.reddit_client_id, s.reddit_client_secret), headers={"User-Agent": s.crawler_user_agent}, timeout=20)
        r.raise_for_status()
        _reddit_token.update(token=r.json()["access_token"], exp=now + 3000)
    sub = (src.config or {}).get("subreddit")
    r = httpx.get(f"https://oauth.reddit.com/r/{sub}/new", params={"limit": 50}, headers={"Authorization": f"bearer {_reddit_token['token']}", "User-Agent": s.crawler_user_agent}, timeout=20)
    r.raise_for_status()
    from datetime import datetime, timezone

    out = []
    for ch in r.json().get("data", {}).get("children", []):
        d = ch.get("data", {})
        out.append({"title": d.get("title", ""), "url": "https://www.reddit.com" + d.get("permalink", ""), "snippet": nlp.truncate(d.get("selftext", ""), 500), "content": d.get("selftext", "")[:5000],
                    "published": datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc), "publisher": f"r/{sub}", "author": d.get("author"), "item_type": "post"})
    return out


def fetch_source_items(src: Source, fetcher: PoliteFetcher) -> tuple[list[dict], dict]:
    """Returns (items, meta). meta may include not_modified, http_status, new_hash, lines."""
    meta: dict = {}
    if src.source_type == "reddit":
        return _reddit_items(src, fetcher), meta
    conditional = src.source_type in ("rss", "web_page", "federal_register", "govuk")
    res = fetcher.get(src.url, etag=src.etag if conditional else None, last_modified=src.last_modified if conditional else None, use_cache=False)
    meta["http_status"] = res.status
    meta["etag"] = res.headers.get("etag")
    meta["last_modified"] = res.headers.get("last-modified")
    if res.not_modified:
        meta["not_modified"] = True
        return [], meta
    if src.source_type == "stackexchange":
        return _items_from_stackexchange(src, res.json()), meta
    if src.source_type == "hackernews":
        return _items_from_hn(res.json()), meta
    if src.source_type == "web_page":
        items, new_hash = _page_change(src, res.text)
        meta["new_hash"] = new_hash
        meta["lines"] = _main_text(res.text)[:400]
        return items, meta
    return _items_from_feed(src, res.text), meta


# ---------------------------------------------------------------- persistence / dedup
def store_items(db: Session, company: Company, src: Source, items: list[dict], run: CrawlRun | None) -> tuple[list[RawItem], int, int]:
    """Insert new items and new versions of modified items. Returns (new_records, changed_count, duplicate_count)."""
    created: list[RawItem] = []
    changed = dup = 0
    since = utcnow() - timedelta(days=45)
    seen_in_batch: set[tuple[str, str]] = set()
    for it in items:
        url = it.get("url") or src.url
        if not it.get("title"):
            continue
        url_norm = nlp.normalize_url(url)
        uhash = nlp.sha256(url_norm if it.get("item_type") not in ("page_change", "page_snapshot") else url_norm + "#" + nlp.sha256(it.get("content") or ""))
        body = (it.get("title") or "") + "\n" + (it.get("content") or it.get("snippet") or "")
        chash = nlp.sha256(body)
        if (uhash, chash) in seen_in_batch:
            continue  # same item listed twice in one feed
        seen_in_batch.add((uhash, chash))
        prev = db.scalars(select(RawItem).where(RawItem.company_id == company.id, RawItem.url_hash == uhash).order_by(RawItem.version.desc()).limit(1)).first()
        if prev is not None:
            if src.source_type in ("news_search", "gdelt"):
                continue  # search snippets of the same article vary between queries; not a content modification
            seen_before = db.scalar(select(RawItem.id).where(RawItem.company_id == company.id, RawItem.url_hash == uhash, RawItem.content_hash == chash).limit(1))
            if seen_before:
                continue  # this exact content was already stored (possibly an older version re-published)
        tkey = nlp.title_key(it["title"])
        duplicate_of = None
        if prev is None and tkey and len(tkey) > 15:
            duplicate_of = db.scalars(select(RawItem.id).where(RawItem.company_id == company.id, RawItem.title_key == tkey, RawItem.discovered_at >= since).limit(1)).first()
        published = it.get("published")
        rec = RawItem(
            company_id=company.id,
            source_id=src.id,
            crawl_run_id=run.id if run else None,
            url=url[:2000],
            url_hash=uhash,
            title=it["title"][:1000],
            content=(it.get("content") or None),
            snippet=it.get("snippet") or nlp.truncate(it.get("content") or it["title"], 400),
            publisher=(it.get("publisher") or "")[:300] or None,
            author=(it.get("author") or "")[:300] or None,
            published_at=published,
            date_source=it.get("date_source") or ("feed" if published else "unknown"),
            content_hash=chash,
            title_key=tkey[:300],
            version=(prev.version + 1) if prev else 1,
            item_type=it.get("item_type", "article"),
            duplicate_of_id=duplicate_of,
            extra=it.get("extra") or {},
        )
        db.add(rec)
        created.append(rec)
        if prev is not None:
            changed += 1
        if duplicate_of:
            dup += 1
    db.flush()
    return created, changed, dup


def _mark_health(src: Source, ok: bool, error: str | None = None, status: int | None = None) -> None:
    now = utcnow()
    src.last_checked_at = now
    if ok:
        src.last_success_at = now
        src.consecutive_failures = 0
        src.health_status = "healthy"
        src.last_error = None
        return
    src.consecutive_failures = (src.consecutive_failures or 0) + 1
    src.last_error = (error or "")[:1000]
    if status in (404, 410) or (error and ("Name or service not known" in error or "nodename nor servname" in error)):
        src.health_status = "dead"
    elif error and "robots.txt" in error:
        src.health_status = "blocked"
    elif src.consecutive_failures >= 3:
        src.health_status = "failing"
    else:
        src.health_status = "degraded"


def crawl_source(db: Session, company: Company, src: Source, run: CrawlRun | None, fetcher: PoliteFetcher) -> tuple[CrawlLog, list[RawItem]]:
    t0 = time.time()
    clog = CrawlLog(company_id=company.id, source_id=src.id, crawl_run_id=run.id if run else None, status="success")
    created: list[RawItem] = []
    sp = db.begin_nested()  # savepoint: a storage error in this source must not poison the whole run
    try:
        items, meta = fetch_source_items(src, fetcher)
        clog.http_status = meta.get("http_status")
        if meta.get("etag"):
            src.etag = meta["etag"][:300]
        if meta.get("last_modified"):
            src.last_modified = meta["last_modified"][:100]
        if meta.get("not_modified"):
            clog.status = "not_modified"
        clog.items_found = len(items)
        created, changed, dup = store_items(db, company, src, items, run)
        if src.source_type == "web_page" and meta.get("new_hash"):
            src.content_hash = meta["new_hash"]
            src.config = {**(src.config or {}), "last_lines": meta.get("lines", [])}
        clog.new_items = len(created) - changed
        clog.changed_items = changed
        if run:
            run.duplicates_skipped += dup
        if created:
            src.last_new_item_at = max([c.published_at or c.discovered_at for c in created])
        _mark_health(src, True)
        sp.commit()
    except RobotsDisallowed as exc:
        clog.status, clog.error = "blocked_robots", str(exc)
        _mark_health(src, False, str(exc))
    except (FetchError, httpx.HTTPError, ValueError) as exc:
        clog.status, clog.error = "error", str(exc)[:1000]
        _mark_health(src, False, str(exc), getattr(exc, "status", None))
    except Exception as exc:  # defensive: never let one source crash the run
        log.exception("unexpected crawl error", extra={"source_id": src.id})
        try:
            sp.rollback()  # also required when the savepoint was deactivated by a failed flush
        except Exception:  # pragma: no cover
            log.exception("savepoint rollback failed")
        created = []
        clog.status, clog.error = "error", f"{type(exc).__name__}: {exc}"[:1000]
        _mark_health(src, False, str(exc))
    if sp.is_active and not getattr(sp, "_committed_or_rolled", False):
        try:
            sp.commit()
        except Exception:  # pragma: no cover
            sp.rollback()
    clog.duration_ms = int((time.time() - t0) * 1000)
    db.add(clog)
    db.flush()
    return clog, created


def crawl_company(db: Session, company: Company, trigger: str = "manual", job_run_id: int | None = None, source_ids: list[int] | None = None,
                  fetcher: PoliteFetcher | None = None, analyze: bool = True, commit_each: bool = True) -> CrawlRun:
    from app.services.analysis import analyze_items

    fetcher = fetcher or get_fetcher()
    run = CrawlRun(company_id=company.id, trigger=trigger, job_run_id=job_run_id)
    db.add(run)
    db.flush()
    q = select(Source).where(Source.company_id == company.id, Source.approval_status == "approved", Source.monitoring_status == "active")
    if source_ids:
        q = select(Source).where(Source.company_id == company.id, Source.id.in_(source_ids))
    sources = list(db.scalars(q.order_by(Source.id)))
    all_new: list[RawItem] = []
    for src in sources:
        clog, created = crawl_source(db, company, src, run, fetcher)
        run.sources_checked += 1
        run.items_seen += clog.items_found
        if clog.status in ("error", "blocked_robots"):
            run.sources_failed += 1
        run.new_items += clog.new_items
        run.changed_items += clog.changed_items
        all_new.extend(created)
        if commit_each:
            db.commit()
    if analyze and all_new:
        signals = analyze_items(db, company, all_new)
        run.signals_created = len(signals)
    run.finished_at = utcnow()
    if run.sources_checked and run.sources_failed == run.sources_checked:
        run.status = "failed"
    elif run.sources_failed:
        run.status = "partial"
    else:
        run.status = "success"
    run.message = f"{run.sources_checked} sources checked, {run.new_items} new and {run.changed_items} changed items, {run.sources_failed} failed, {run.signals_created} signals."
    db.flush()
    return run


TAG_RE = re.compile(r"<[^>]+>")
