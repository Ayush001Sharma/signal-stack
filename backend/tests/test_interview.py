from app.models import Competitor, InterviewQuestion, ProfileFact
from app.services.interview import TOPICS, answer_question, generate_questions, next_question, ordered_questions

EDU = {"products": ["University Selection and Application", "Visa and Immigration Support"], "customer_segments": ["Students", "Parents"], "geographies": ["United Kingdom", "Canada", "India"], "business_model": ["Services / consulting fees"], "industry": "Education / study-abroad services"}
PAY = {"products": ["Payment Gateway", "Payroll", "Business Banking"], "customer_segments": ["Small & medium businesses", "Enterprises", "Developers"], "geographies": ["India", "Malaysia"], "business_model": ["Transaction / payments fees"], "industry": "Fintech / payments"}


def test_questions_are_ten_grounded_and_company_specific(db, make_company):
    a = make_company("Acme Study", "https://acme.example", profile=EDU, keywords=["study abroad", "student visa"])
    b = make_company("PayCo", "https://payco.example", profile=PAY, keywords=["payment gateway", "payouts"])
    db.add(Competitor(company_id=a.id, name="Leverage Edu", name_key="leverageedu", status="suggested", confidence=0.8, evidence=[]))
    db.flush()
    qa = generate_questions(db, a, use_llm=False)
    qb = generate_questions(db, b, use_llm=False)
    assert len(qa) == 10 and len(qb) == 10
    assert [q.topic for q in qa] == TOPICS
    texts_a, texts_b = [q.question for q in qa], [q.question for q in qb]
    assert len(set(texts_a)) == 10  # no repeats
    assert not set(texts_a) & set(texts_b)  # differ between companies
    joined_a = " ".join(texts_a)
    assert "Leverage Edu" in joined_a and "Visa and Immigration Support" in joined_a
    assert "Payment Gateway" in " ".join(texts_b)
    assert all(q.rationale for q in qa)


def test_answer_updates_profile_and_creates_followup(db, make_company):
    c = make_company("Acme Study", "https://acme.example", profile=EDU, keywords=["study abroad"])
    generate_questions(db, c, use_llm=False)
    q = next_question(db, c.id)
    assert q.topic == "revenue_streams" and q.position == 1
    res = answer_question(db, c, q, "Counselling fees", use_llm=False)  # short answer -> probe follow-up
    assert q.status == "answered"
    fact = db.query(ProfileFact).filter_by(company_id=c.id, source_url=f"interview:{q.id}").one()
    assert fact.status == "verified" and fact.origin == "interview" and fact.value == "Counselling fees"
    assert res["followup_id"]
    fu = db.get(InterviewQuestion, res["followup_id"])
    assert fu.is_followup and fu.parent_id == q.id and fu.sort_key == q.sort_key + 0.5
    assert next_question(db, c.id).id == fu.id  # follow-up asked next (one at a time)
    # editing an answer replaces the fact rather than duplicating, and does not create another follow-up
    res2 = answer_question(db, c, q, "Counselling fees (70%) and university referral commissions (30%)", use_llm=False)
    facts = db.query(ProfileFact).filter_by(company_id=c.id, source_url=f"interview:{q.id}").all()
    assert len(facts) == 1 and "referral" in facts[0].value and res2["followup_id"] is None


def test_competitor_answer_and_skip(db, make_company):
    c = make_company("Acme Study", "https://acme.example", profile=EDU, keywords=["study abroad"])
    db.add(Competitor(company_id=c.id, name="Yocket", name_key="yocket", status="suggested", confidence=0.6, evidence=[]))
    db.flush()
    qs = {q.topic: q for q in generate_questions(db, c, use_llm=False)}
    res = answer_question(db, c, qs["competitors"], "We mostly lose students to Leverage Edu and IDP Education. Yocket is irrelevant for us.", use_llm=False)
    comps = {x.name: x.status for x in db.query(Competitor).filter_by(company_id=c.id)}
    assert comps.get("Leverage Edu") == "confirmed" and comps.get("IDP Education") == "confirmed"
    assert comps["Yocket"] == "rejected"
    assert "Leverage Edu" in res["changes"]["competitors_added"]
    answer_question(db, c, qs["risks"], None, skip=True, confidential=True, use_llm=False)
    assert qs["risks"].status == "skipped" and qs["risks"].confidential
    f = db.query(ProfileFact).filter_by(company_id=c.id, source_url=f"interview:{qs['risks'].id}").one()
    assert f.status == "needs_confirmation"


def test_interview_api_flow(client, db, make_company):
    c = make_company("Acme Study", "https://acme.example", profile=EDU, keywords=["study abroad"], status="researched")
    db.commit()
    qs = client.post(f"/api/companies/{c.id}/interview/generate?use_llm=false").json()
    assert len(qs) == 10
    st = client.get(f"/api/companies/{c.id}/interview").json()
    assert st["next"]["id"] == qs[0]["id"] and st["progress"]["pending"] == 10
    r = client.post(f"/api/companies/{c.id}/interview/questions/{qs[0]['id']}/answer?use_llm=false", json={"answer": "Most revenue comes from premium counselling packages sold to postgraduate students going to the UK."})
    assert r.status_code == 200 and r.json()["question"]["status"] == "answered"
    assert client.post(f"/api/companies/{c.id}/interview/questions/{qs[1]['id']}/answer", json={}).status_code == 422
    # persistence
    again = client.get(f"/api/companies/{c.id}/interview").json()
    assert again["progress"]["answered"] == 1
    assert len(ordered_questions(db, c.id)) >= 10


def test_non_founder_answers_are_not_verified(db, make_company):
    c = make_company("Acme Study", "https://acme.example", profile=EDU, keywords=["study abroad"])
    qs = {q.topic: q for q in generate_questions(db, c, use_llm=False)}
    answer_question(db, c, qs["competitors"], "Probably Leverage Edu and IDP Education based on public news.", use_llm=False, answered_by="demo_operator")
    f = db.query(ProfileFact).filter_by(company_id=c.id, source_url=f"interview:{qs['competitors'].id}").one()
    assert f.status == "assumption" and "NOT the founder" in f.evidence
    assert db.query(Competitor).filter_by(company_id=c.id).count() == 0  # demo input cannot confirm competitors
    assert qs["competitors"].answered_by == "demo_operator"
