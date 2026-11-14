from app.models import CrawlLog, RawItem, Signal, Source
from app.services.crawler import crawl_company
from tests.conftest import rss

FEED_URL = "https://news.example/feed"


def _src(db, c, url=FEED_URL, kind="rss", category="market", name="Industry feed", **kw):
    s = Source(company_id=c.id, name=name, url=url, normalized_url=url, category=category, source_type=kind, approval_status="approved", credibility=0.7, **kw)
    db.add(s)
    db.flush()
    return s


ITEMS = [
    {"title": "UK announces new student visa rules for international students", "link": "https://news.example/a", "desc": "The UK government will tighten student visa rules from January, affecting international students and universities.", "date": "Tue, 10 Nov 2026 08:00:00 GMT"},
    {"title": "Canada caps study permits again", "link": "https://news.example/b", "desc": "Canada will cap study permits for international students in 2027.", "date": "Wed, 11 Nov 2026 08:00:00 GMT"},
]


def test_crawl_stores_new_items_dedups_and_versions(db, make_company, web):
    c = make_company(keywords=["international students", "student visa", "study abroad"], profile={"one_liner": "study abroad counselling for international students", "geographies": ["United Kingdom", "Canada"]})
    s = _src(db, c)
    web.add(FEED_URL, rss(ITEMS), headers={"content-type": "application/rss+xml"})
    run1 = crawl_company(db, c, fetcher=web.fetcher())
    assert run1.status == "success" and run1.new_items == 2 and run1.signals_created == 2
    items = db.query(RawItem).filter_by(company_id=c.id).all()
    assert {i.url for i in items} == {"https://news.example/a", "https://news.example/b"}
    assert all(i.published_at is not None and i.snippet for i in items)
    # second crawl: nothing new
    run2 = crawl_company(db, c, fetcher=web.fetcher())
    assert run2.new_items == 0 and run2.changed_items == 0
    # modified content at the same URL -> new version, history preserved
    changed = [dict(ITEMS[0], desc="UPDATED: rules now apply from March."), ITEMS[1]]
    web.add(FEED_URL, rss(changed), headers={"content-type": "application/rss+xml"})
    run3 = crawl_company(db, c, fetcher=web.fetcher())
    assert run3.changed_items == 1
    versions = db.query(RawItem).filter_by(company_id=c.id, url="https://news.example/a").order_by(RawItem.version).all()
    assert [v.version for v in versions] == [1, 2]
    assert s.health_status == "healthy" and s.last_success_at is not None
    assert db.query(CrawlLog).filter_by(source_id=s.id).count() == 3


def test_cross_source_duplicate_story_corroborates(db, make_company, web):
    c = make_company(keywords=["student visa"], profile={"one_liner": "student visa help"})
    _src(db, c, url="https://news.example/feed", name="Feed A")
    _src(db, c, url="https://other.example/feed", name="Feed B")
    web.add("https://news.example/feed", rss([ITEMS[0]]), headers={"content-type": "application/rss+xml"})
    web.add("https://other.example/feed", rss([dict(ITEMS[0], link="https://other.example/story")]), headers={"content-type": "application/rss+xml"})
    run = crawl_company(db, c, fetcher=web.fetcher())
    assert run.duplicates_skipped == 1
    sigs = db.query(Signal).filter_by(company_id=c.id).all()
    assert len(sigs) == 1 and sigs[0].corroboration_count == 2 and sigs[0].verification_status == "corroborated"


def test_failures_do_not_crash_run(db, make_company, web):
    c = make_company(keywords=["student visa"])
    ok = _src(db, c, name="ok")
    gone = _src(db, c, url="https://gone.example/feed", name="gone")
    blocked = _src(db, c, url="https://blocked.example/feed", name="blocked")
    web.add(FEED_URL, rss(ITEMS), headers={"content-type": "application/rss+xml"})
    web.add("https://gone.example/feed", "gone", status=404)
    web.add("https://blocked.example/robots.txt", "User-agent: *\nDisallow: /", headers={"content-type": "text/plain"})
    run = crawl_company(db, c, fetcher=web.fetcher())
    assert run.status == "partial" and run.sources_checked == 3 and run.sources_failed == 2
    assert ok.health_status == "healthy" and gone.health_status == "dead" and blocked.health_status == "blocked"
    logs = {l.source_id: l.status for l in db.query(CrawlLog).filter_by(company_id=c.id)}
    assert logs[blocked.id] == "blocked_robots" and logs[gone.id] == "error"
    assert "https://blocked.example/feed" not in web.calls  # never fetched


def test_paused_sources_are_skipped(db, make_company, web):
    c = make_company()
    s = _src(db, c, monitoring_status="paused")
    run = crawl_company(db, c, fetcher=web.fetcher())
    assert run.sources_checked == 0 and s.last_checked_at is None


def test_web_page_change_detection(db, make_company, web):
    c = make_company(keywords=["pricing"], profile={"one_liner": "study abroad"})
    s = _src(db, c, url="https://rival.example/pricing", kind="web_page", category="competitors", name="Rival pricing page (change monitor)")
    v1 = "<html><body><main><p>Premium counselling plan costs 50,000 per student per year.</p><p>Includes five university applications and visa guidance.</p></main></body></html>"
    web.add("https://rival.example/pricing", v1)
    crawl_company(db, c, fetcher=web.fetcher())
    snap = db.query(RawItem).filter_by(source_id=s.id).one()
    assert snap.item_type == "page_snapshot" and db.query(Signal).count() == 0  # baseline is not a signal
    web.add("https://rival.example/pricing", v1.replace("50,000", "35,000").replace("five", "eight"))
    run = crawl_company(db, c, fetcher=web.fetcher())
    change = db.query(RawItem).filter_by(source_id=s.id, item_type="page_change").one()
    assert "35,000" in change.content and "50,000" in change.content
    sig = db.query(Signal).filter_by(raw_item_id=change.id).one()
    assert sig.signal_type == "pricing" and sig.verification_status == "observed_change"
    assert run.changed_items == 0 and run.new_items == 1


def test_duplicate_entries_in_one_feed_are_stored_once(db, make_company, web):
    c = make_company(keywords=["student visa"])
    _src(db, c)
    web.add(FEED_URL, rss([ITEMS[0], ITEMS[0], ITEMS[1]]), headers={"content-type": "application/rss+xml"})
    run = crawl_company(db, c, fetcher=web.fetcher())
    assert run.status == "success" and run.new_items == 2


def test_storage_error_in_one_source_is_isolated(db, make_company, web, monkeypatch):
    import app.services.crawler as cr

    c = make_company(keywords=["student visa"])
    bad = _src(db, c, url="https://bad.example/feed", name="bad")
    good = _src(db, c, url="https://good.example/feed", name="good")
    web.add("https://bad.example/feed", rss([ITEMS[0]]), headers={"content-type": "application/rss+xml"})
    web.add("https://good.example/feed", rss([ITEMS[1]]), headers={"content-type": "application/rss+xml"})
    orig = cr.store_items

    def flaky(db_, company, src, items, run):
        if src.name == "bad":
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("insert", {}, Exception("duplicate key"))
        return orig(db_, company, src, items, run)

    monkeypatch.setattr(cr, "store_items", flaky)
    run = crawl_company(db, c, fetcher=web.fetcher())
    assert run.status == "partial" and run.new_items == 1
    assert bad.health_status == "degraded" and good.health_status == "healthy"
    assert db.query(RawItem).filter_by(company_id=c.id).count() == 1


def test_flapping_content_does_not_duplicate(db, make_company, web):
    c = make_company(keywords=["student visa"])
    _src(db, c)
    a = rss([ITEMS[0]])
    b = rss([dict(ITEMS[0], desc="Alternative wording of the same story.")])
    for body in (a, b, a, b):
        web.add(FEED_URL, body, headers={"content-type": "application/rss+xml"})
        run = crawl_company(db, c, fetcher=web.fetcher())
        assert run.status == "success"
    assert db.query(RawItem).filter_by(company_id=c.id).count() == 2  # two distinct versions, no duplicates


def test_news_search_snippet_variation_is_not_a_modification(db, make_company, web):
    c = make_company(keywords=["student visa"])
    s = _src(db, c, url="https://www.bing.com/news/search?q=x&format=rss", kind="news_search")
    web.add("https://www.bing.com/news/search?q=x&format=rss", rss([ITEMS[0]]), headers={"content-type": "application/rss+xml"})
    crawl_company(db, c, fetcher=web.fetcher())
    web.add("https://www.bing.com/news/search?q=x&format=rss", rss([dict(ITEMS[0], desc="other snippet")]), headers={"content-type": "application/rss+xml"})
    run = crawl_company(db, c, fetcher=web.fetcher())
    assert run.changed_items == 0 and db.query(RawItem).filter_by(source_id=s.id).count() == 1


def test_real_db_constraint_violation_is_isolated(db, make_company, web, monkeypatch):
    """A genuine unique-constraint failure during flush in one source must not poison the session."""
    import app.services.crawler as cr

    c = make_company(keywords=["student visa"])
    bad = _src(db, c, url="https://bad.example/feed", name="bad")
    good = _src(db, c, url="https://good.example/feed", name="good")
    web.add("https://bad.example/feed", rss([ITEMS[0]]), headers={"content-type": "application/rss+xml"})
    web.add("https://good.example/feed", rss([ITEMS[1]]), headers={"content-type": "application/rss+xml"})
    orig = cr.store_items

    def violating(db_, company, src, items, run):
        if src.name == "bad":
            for _ in range(2):  # two identical rows -> real UniqueViolation on flush
                db_.add(RawItem(company_id=company.id, source_id=src.id, url="u", url_hash="same", title="t", content_hash="same", title_key="t"))
            db_.flush()
        return orig(db_, company, src, items, run)

    monkeypatch.setattr(cr, "store_items", violating)
    run = crawl_company(db, c, fetcher=web.fetcher())
    db.commit()
    assert run.status == "partial" and good.health_status == "healthy" and bad.health_status == "degraded"
    assert db.query(RawItem).filter_by(company_id=c.id).count() == 1
