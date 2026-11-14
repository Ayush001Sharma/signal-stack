from datetime import timedelta

from app.models import BriefAction, Signal, utcnow
from app.services.briefs import generate_brief, render_markdown, render_pdf

SECTIONS = ["## 1. Executive Summary", "## 2. Customer Signals", "## 3. Competitor Intelligence", "## 4. Market Intelligence", "## 5. Internal Business Intelligence",
            "## 6. Opportunities Identified", "## 7. Risks & Threats", "## 8. Recommended Actions for This Week", "## 9. What We Should Watch", "## 10. Source Appendix"]


def _sig(db, c, title, category="market", polarity="neutral", score=50.0, days_ago=2, meaningful=True, **kw):
    s = Signal(company_id=c.id, category=category, signal_type=kw.pop("signal_type", "industry_news"), title=title, what_happened=title, event_date=utcnow() - timedelta(days=days_ago),
               evidence_url=f"https://n.example/{abs(hash(title))}", evidence_snippet=f"Evidence for {title}", publisher="Reuters", verification_status=kw.pop("verification_status", "single_source_report"),
               source_reliability=0.8, evidence_strength=0.6, relevance=0.7, impact=0.6, urgency=0.5, novelty=1, recency=0.9, priority_score=score, priority="high" if score >= 60 else "medium",
               polarity=polarity, business_area="Strategy", why_it_matters="Because it affects us", recommended_action=f"Act on {title}", is_meaningful=meaningful, cluster_key=title.lower(), **kw)
    db.add(s)
    db.flush()
    return s


def test_brief_structure_and_evidence(db, make_company):
    c = make_company()
    _sig(db, c, "Regulator caps permits", polarity="threat", score=72, signal_type="regulation", materiality="material")
    _sig(db, c, "Rival launches product", category="competitors", polarity="threat", score=65)
    _sig(db, c, "Students complain about delays", category="customers", polarity="opportunity", score=58, verification_status="community_claim")
    _sig(db, c, "Scholarship fund expanded", polarity="opportunity", score=55)
    _sig(db, c, "New market demand", polarity="opportunity", score=50)
    _sig(db, c, "Ancient story", score=90, days_ago=200)  # outside window
    _sig(db, c, "Irrelevant item", score=95, meaningful=False)  # not meaningful
    b = generate_brief(db, c, lookback_days=14, use_llm=False)
    md = b.markdown
    positions = [md.index(s) for s in SECTIONS]
    assert positions == sorted(positions)  # exact order
    content = b.content
    assert len(content["executive_summary"]) == 5
    titles = [i["title"] for i in content["executive_summary"]]
    assert "Ancient story" not in titles and "Irrelevant item" not in titles
    assert titles[0] == "Regulator caps permits"
    assert len(content["opportunities"]) >= 3 and content["opportunities_note"] is None
    assert content["risks"] and content["recommended_actions"]
    # every cited item is in the appendix with a link, dates, snippet and verification
    refs = {a["ref"] for a in content["source_appendix"]}
    for i in content["executive_summary"]:
        assert i["ref"] in refs and i["evidence_url"].startswith("https://")
    for a in content["source_appendix"]:
        assert a["url"] and a["published"] and a["discovered"] and a["snippet"] and a["verification"]
    assert content["internal_intelligence"]["empty_message"]  # no uploads -> says so explicitly
    assert db.query(BriefAction).filter_by(brief_id=b.id).count() == len(content["recommended_actions"])
    assert render_pdf(b)[:4] == b"%PDF"


def test_empty_brief_states_no_developments(db, make_company):
    c = make_company()
    b = generate_brief(db, c, lookback_days=7, use_llm=False)
    ct = b.content
    assert ct["executive_summary"] == [] and ct["source_appendix"] == []
    assert "No meaningful" in ct["customer_signals"]["empty_message"]
    assert "No meaningful competitor" in ct["competitor_intelligence"]["empty_message"]
    assert "Only 0 opportunities" in ct["opportunities_note"]
    assert "no invented items" in ct["narrative"]["text"]
    assert "No meaningful developments were detected" in render_markdown(b)


def test_brief_api_exports_and_actions(client, db, make_company):
    c = make_company()
    _sig(db, c, "Regulator caps permits", polarity="threat", score=72)
    b = generate_brief(db, c, lookback_days=14, use_llm=False)
    db.commit()
    assert client.get(f"/api/companies/{c.id}/briefs").json()["total"] == 1
    assert client.get(f"/api/companies/{c.id}/briefs/latest").json()["id"] == b.id
    md = client.get(f"/api/companies/{c.id}/briefs/{b.id}/markdown")
    assert md.status_code == 200 and "## 10. Source Appendix" in md.text
    assert client.get(f"/api/companies/{c.id}/briefs/{b.id}/pdf").content[:4] == b"%PDF"
    assert "<table" in client.get(f"/api/companies/{c.id}/briefs/{b.id}/html").text
    acts = client.get(f"/api/companies/{c.id}/briefs/{b.id}/actions").json()
    r = client.patch(f"/api/companies/{c.id}/actions/{acts[0]['id']}", json={"status": "done"})
    assert r.json()["status"] == "done"
    other = client.post("/api/companies", json={"name": "Other", "website": "https://other.example", "run_setup": False}).json()
    assert client.get(f"/api/companies/{other['id']}/briefs/{b.id}").status_code == 404


def test_synthetic_internal_data_is_confined_to_section_5(db, make_company):
    from app.models import InternalDocument

    c = make_company()
    doc = InternalDocument(company_id=c.id, filename="SYNTHETIC_DEMO_crm.csv", stored_path="/tmp/x", content_type="text/csv", file_type="csv", size_bytes=1, sha256="x", status="processed", description="synthetic test data")
    db.add(doc)
    db.flush()
    _sig(db, c, "Lost-deal reason: too expensive", category="internal", polarity="threat", score=95, document_id=doc.id, verification_status="internal_document")
    _sig(db, c, "Regulator caps permits", polarity="threat", score=60)
    b = generate_brief(db, c, lookback_days=14, use_llm=False)
    ct = b.content
    assert [i["title"] for i in ct["executive_summary"]] == ["Regulator caps permits"]
    assert all(i["category"] != "internal" for i in ct["risks"] + ct["opportunities"])
    assert ct["internal_intelligence"]["items"] and ct["internal_intelligence"]["synthetic_note"]
    assert "SYNTHETIC TEST DATA" in b.markdown
