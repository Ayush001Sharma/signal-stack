from datetime import timedelta

from app.models import RawItem, Source, utcnow
from app.services import nlp
from app.services.audit import reassess_context, run_audit
from tests.conftest import rss


def _src(db, c, name, url, **kw):
    s = Source(company_id=c.id, name=name, url=url, normalized_url=nlp.normalize_url(url), category=kw.pop("category", "market"), source_type=kw.pop("source_type", "rss"), approval_status="approved", **kw)
    db.add(s)
    db.flush()
    return s


def test_monthly_audit_detects_dead_duplicate_inactive(db, make_company, web):
    c = make_company(keywords=["student visa"], profile={"one_liner": "student visa counselling"})
    alive = _src(db, c, "Alive", "https://alive.example/feed", last_new_item_at=utcnow() - timedelta(days=2))
    dead = _src(db, c, "Dead", "https://dead.example/feed", last_new_item_at=utcnow() - timedelta(days=3))
    stale = _src(db, c, "Stale", "https://stale.example/feed", last_new_item_at=utcnow() - timedelta(days=200))
    dup = _src(db, c, "Alive", "https://alive-mirror.example/feed", last_new_item_at=utcnow())
    web.add("https://alive.example/feed", rss([{"title": "student visa news", "link": "https://alive.example/1"}]), headers={"content-type": "application/rss+xml"})
    web.add("https://stale.example/feed", rss([]), headers={"content-type": "application/rss+xml"})
    web.add("https://alive-mirror.example/feed", rss([]), headers={"content-type": "application/rss+xml"})
    web.add("https://dead.example/feed", "gone", status=404)
    rep = run_audit(db, c, fetcher=web.fetcher(), discover=False)
    s = rep.content["summary"]
    assert s["dead_or_unavailable"] == 1 and dead.health_status == "dead"
    assert rep.content["duplicates"] == [{"source_id": dup.id, "duplicate_of": alive.id}]
    assert [i["name"] for i in rep.content["inactive"]] == ["Stale"]
    removal_ids = {r["source_id"] for r in rep.content["recommend_remove"]}
    assert {dead.id, dup.id} <= removal_ids
    assert "## Dead / unavailable sources" in rep.markdown


def test_audit_api_and_failed_job_visibility(client, db, make_company, monkeypatch):
    c = make_company()
    db.commit()
    import app.services.jobs as jobs_mod

    def boom(db, company, run, **kw):
        raise ConnectionError("network down")

    monkeypatch.setitem(jobs_mod.JOB_FUNCS, "monthly_audit", boom)
    jobs_mod.start_job("monthly_audit", c.id, background=False, trigger="scheduled")
    failed = client.get(f"/api/jobs?company_id={c.id}&status=failed").json()
    assert failed["total"] == 1 and "network down" in failed["items"][0]["message"]
    dash = client.get(f"/api/companies/{c.id}/dashboard").json()
    assert dash["failed_jobs"][0]["job_type"] == "monthly_audit"


def test_context_change_reassesses_sources(db, make_company, web):
    c = make_company(keywords=["student visa", "study abroad"], profile={"one_liner": "study abroad counselling"})
    edu = _src(db, c, "Visa news", "https://visa.example/feed")
    db.add(RawItem(company_id=c.id, source_id=edu.id, url="https://visa.example/1", url_hash="h1", title="Student visa rules for study abroad applicants change", content_hash="c1", title_key="k1"))
    loans = _src(db, c, "Loan news", "https://loans.example/feed")
    db.add(RawItem(company_id=c.id, source_id=loans.id, url="https://loans.example/1", url_hash="h2", title="Education loan interest rates fall for overseas education loans", content_hash="c2", title_key="k2"))
    db.flush()
    cc = reassess_context(db, c, "Fintech / education loans", "We now focus on education loans and loan interest rates for overseas education loans", fetcher=web.fetcher(), discover=False)
    deltas = {r["name"]: r["delta"] for r in cc.relevance_changes}
    assert deltas["Loan news"] > deltas["Visa news"]
    assert "education loans" in " ".join(cc.added_keywords)
    assert c.keywords[0] in cc.added_keywords and c.industry == "Fintech / education loans"
    assert "re-scored" in cc.summary
