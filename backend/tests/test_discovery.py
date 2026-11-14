from app.models import Competitor, Source
from app.services import nlp
from app.services.discovery import Discovery, credibility_for, mark_duplicates, publisher_reliability
from tests.conftest import rss


def test_normalize_url_and_credibility():
    assert nlp.normalize_url("http://www.Example.com/a/?utm_source=x&b=2") == "https://example.com/a?b=2"
    assert credibility_for("https://www.gov.uk/x", "govuk")[1] == "official"
    assert credibility_for("https://api.stackexchange.com/x", "stackexchange")[1] == "community"
    assert credibility_for("https://www.bing.com/news/search?q=x", "news_search")[1] == "aggregated"
    assert publisher_reliability("Reuters", "https://www.reuters.com/x") > publisher_reliability("Some Blog", "https://blog.example/x")


def _probe(rel=0.6, count=5):
    from datetime import datetime, timezone

    return {"items": [{"title": "x"}] * count, "count": count, "relevance": rel, "why": "test", "latest": datetime.now(timezone.utc), "frequency": "daily", "sample": []}


def test_discovery_add_recommends_and_dedupes(db, make_company, web):
    c = make_company(keywords=["study abroad"])
    d = Discovery(db, c, web.fetcher())
    s1 = d.add(name="Good feed", url="https://pub.example/feed", category="market", source_type="rss", description="d", reason="r", probe=_probe(0.7))
    s2 = d.add(name="Weak feed", url="https://weak.example/feed", category="market", source_type="rss", description="d", reason="r", probe=_probe(0.1))
    dup = d.add(name="Good feed again", url="https://www.pub.example/feed/", category="market", source_type="rss", description="d", reason="r", probe=_probe(0.7))
    dead = d.add(name="Dead", url="https://dead.example/feed", category="market", source_type="rss", description="d", reason="r", probe=None)
    assert s1.recommended and s1.approval_status == "pending" and s1.reason == "r" and s1.credibility_rationale
    assert not s2.recommended and "below threshold" in s2.relevance_rationale
    assert dup is None and dead is None
    assert {x["why"] for x in d.skipped} == {"duplicate of existing source", "unreachable or disallowed by robots.txt"}


def test_mark_duplicates_by_name(db, make_company):
    c = make_company()
    a = Source(company_id=c.id, name="Competitor news: Yocket", url="https://a.example/1", normalized_url="https://a.example/1", category="competitors", source_type="news_search")
    b = Source(company_id=c.id, name="Competitor news: Yocket", url="https://b.example/2", normalized_url="https://b.example/2", category="competitors", source_type="news_search")
    db.add_all([a, b])
    db.flush()
    pairs = mark_duplicates(db, c.id)
    assert pairs == [(b.id, a.id)] and b.duplicate_of_id == a.id


def test_competitor_sources_discovered_from_competitors(db, make_company, web):
    c = make_company(keywords=["study abroad"], profile={"one_liner": "study abroad counselling"})
    comp = Competitor(company_id=c.id, name="Yocket", name_key="yocket", website="https://yocket.example", status="confirmed", confidence=0.9, evidence=[], reason="founder named")
    db.add(comp)
    db.flush()
    web.add("https://www.bing.com/news/search*", rss([{"title": "Yocket launches study abroad loan product", "link": "https://n.example/1", "desc": "Yocket, the study abroad platform, launched loans."}]), headers={"content-type": "application/rss+xml"})
    web.add("https://yocket.example", '<html><head><link rel="alternate" type="application/rss+xml" href="/blog/feed"></head><body>Yocket</body></html>')
    web.add("https://yocket.example/blog/feed", rss([{"title": "Yocket blog: new GRE prep", "link": "https://yocket.example/blog/1"}]), headers={"content-type": "application/rss+xml"})
    d = Discovery(db, c, web.fetcher())
    d.competitors()
    names = {s.name: s for s in d.created}
    assert "Competitor news: Yocket" in names and "Yocket blog/newsroom feed" in names
    assert all(s.competitor_id == comp.id and s.category == "competitors" for s in d.created)
    assert names["Yocket blog/newsroom feed"].credibility_label == "primary"


def test_source_approval_api(client, db, make_company):
    c = make_company()
    for i, rec in enumerate([True, True, False]):
        db.add(Source(company_id=c.id, name=f"S{i}", url=f"https://s{i}.example/feed", normalized_url=f"https://s{i}.example/feed", category="market", source_type="rss", recommended=rec))
    db.commit()
    r = client.post(f"/api/companies/{c.id}/sources/bulk", json={"action": "approve_recommended"})
    assert r.json()["updated"] == 2
    srcs = client.get(f"/api/companies/{c.id}/sources").json()
    by = {s["name"]: s for s in srcs}
    assert by["S0"]["approval_status"] == "approved" and by["S2"]["approval_status"] == "pending"
    assert client.patch(f"/api/companies/{c.id}/sources/{by['S2']['id']}", json={"approval_status": "rejected"}).json()["approval_status"] == "rejected"
    assert client.patch(f"/api/companies/{c.id}/sources/{by['S0']['id']}", json={"monitoring_status": "paused"}).json()["monitoring_status"] == "paused"
    assert client.delete(f"/api/companies/{c.id}/sources/{by['S1']['id']}").status_code == 204
    remaining = {s["name"] for s in client.get(f"/api/companies/{c.id}/sources").json()}
    assert "S1" not in remaining
    assert "S1" in {s["name"] for s in client.get(f"/api/companies/{c.id}/sources?include_removed=true").json()}


def test_manual_source_add_duplicate_and_isolation(client, db, make_company, monkeypatch, web):
    a = make_company("A Co", "https://a.example")
    b = make_company("B Co", "https://b.example")
    db.commit()
    web.add("https://feeds.example/rss", rss([{"title": "Industry update", "link": "https://feeds.example/1"}]), headers={"content-type": "application/rss+xml"})
    import app.api.sources as mod

    monkeypatch.setattr(mod, "get_fetcher", lambda: web.fetcher())
    body = {"name": "Industry feed", "url": "https://feeds.example/rss", "category": "market", "source_type": "rss", "reason": "Covers our industry"}
    r = client.post(f"/api/companies/{a.id}/sources", json=body)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["approval_status"] == "approved" and r.json()["discovered_by"] == "user"
    assert client.post(f"/api/companies/{a.id}/sources", json=body).status_code == 409
    # company B cannot see or modify company A's source
    assert client.get(f"/api/companies/{b.id}/sources/{sid}/history").status_code == 404
    assert client.patch(f"/api/companies/{b.id}/sources/{sid}", json={"monitoring_status": "paused"}).status_code == 404
