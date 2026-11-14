from urllib.parse import parse_qs, urlparse

import httpx

from app.services.competitors import category_queries, discover_competitors
from app.services.fetcher import PoliteFetcher
from tests.conftest import rss

PROFILE = {"one_liner": "study abroad counselling for Indian students", "industry": "Education / study-abroad services", "geographies": ["India", "United Kingdom"], "meta_keywords": ["study abroad"]}


def _news(q: str) -> str:
    q = q.lower()
    if '"rivalcorp"' in q:
        return rss([{"title": f"RivalCorp item {i}", "link": f"https://n.example/r{i}", "desc": f"RivalCorp offers study abroad counselling for Indian students and overseas education admissions support, item {i}."} for i in range(4)])
    if '"zentrix"' in q:
        return rss([{"title": f"Zentrix item {i}", "link": f"https://n.example/z{i}", "desc": f"Zentrix reported quarterly steel production and mining output {i}."} for i in range(4)])
    if '"' in q:
        return rss([])
    return rss([
        {"title": "Study abroad market heats up", "link": "https://n.example/a", "desc": "RivalCorp and Zentrix were named in a study abroad report."},
        {"title": "Funding round for study abroad startup", "link": "https://n.example/b", "desc": "RivalCorp raised funding while Zentrix also appeared in rankings."},
    ])


def test_competitors_discovered_dynamically_with_evidence(db, make_company):
    c = make_company("Acme Study", "https://acme.example", profile=PROFILE, keywords=["study abroad", "overseas education"])

    def handler(req: httpx.Request):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if "bing.com" in req.url.host:
            return httpx.Response(200, text=_news(parse_qs(urlparse(str(req.url)).query)["q"][0]), headers={"content-type": "application/rss+xml"})
        if req.url.host == "rivalcorp.com" and req.url.path in ("", "/"):
            return httpx.Response(200, text="<html><head><title>RivalCorp | Study abroad</title></head></html>")
        return httpx.Response(404)

    qs = category_queries(c)
    assert any("study abroad" in q for q in qs) and any("India" in q for q in qs)
    comps = discover_competitors(db, c, fetcher=PoliteFetcher(transport=httpx.MockTransport(handler)), use_llm=False)
    names = [x.name for x in comps]
    assert names == ["RivalCorp"]  # Zentrix co-occurs but its own coverage is unrelated -> rejected
    rc = comps[0]
    assert rc.website == "https://rivalcorp.com" and rc.evidence and all(e["url"].startswith("https://") for e in rc.evidence)
    assert "semantically similar" in rc.reason and rc.status == "suggested"
    trace = {t["name"]: t["decision"] for t in c.research_summary["competitor_discovery"]["candidates"]}
    assert trace["Zentrix"].startswith("rejected")
