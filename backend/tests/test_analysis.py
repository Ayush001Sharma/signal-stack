from datetime import timedelta

from app.models import RawItem, Signal, Source, utcnow
from app.services import nlp
from app.services.analysis import HIGH, WEIGHTS, Analyzer, classify_type


def test_classify_type_rules():
    assert classify_type("Rival raises $20 million Series B", "competitors", "article") == "funding"
    assert classify_type("UK tightens student visa rules", "market", "article") == "regulation"
    assert classify_type("Rival launches new AI counsellor", "competitors", "article") == "product_launch"
    assert classify_type("My visa got rejected again, so frustrating", "customers", "post") == "complaint"
    assert classify_type("Some neutral article", "market", "article") == "industry_news"
    assert classify_type("price changed", "competitors", "page_change") == "pricing"


def _item(db, c, src, title, desc, days_ago=1, url=None):
    it = RawItem(company_id=c.id, source_id=src.id, url=url or f"https://n.example/{abs(hash(title))}", url_hash=nlp.sha256(title), title=title, snippet=desc, publisher="Reuters",
                 published_at=utcnow() - timedelta(days=days_ago) if days_ago is not None else None, content_hash=nlp.sha256(desc), title_key=nlp.title_key(title), item_type="article")
    db.add(it)
    db.flush()
    return it


def test_scores_are_explainable_and_ranked(db, make_company):
    c = make_company(keywords=["student visa", "international students", "study abroad"], profile={"one_liner": "study abroad counselling for international students", "geographies": ["United Kingdom"], "products": ["Visa support"]})
    src = Source(company_id=c.id, name="Market news", url="https://www.bing.com/news/search?q=x", normalized_url="x", category="market", source_type="news_search", approval_status="approved", credibility=0.6)
    db.add(src)
    db.flush()
    relevant = _item(db, c, src, "UK to cap student visa numbers for international students from January", "The UK will cap student visas for international students starting January, a policy affecting study abroad demand.")
    irrelevant = _item(db, c, src, "Football club wins derby", "A local football club won the derby on Sunday.")
    old = _item(db, c, src, "UK student visa policy review published", "Review of student visa policy for international students.", days_ago=300)
    sigs = {s.raw_item_id: s for s in Analyzer(db, c).analyze([relevant, irrelevant, old])}
    s = sigs[relevant.id]
    comps = s.score_breakdown["components"]
    expected = round(100 * sum(WEIGHTS[k] * comps[k] for k in WEIGHTS), 1)
    assert s.priority_score == expected
    assert set(s.score_breakdown["reasons"]) == set(WEIGHTS)
    assert s.signal_type == "regulation" and s.polarity == "threat" and s.is_meaningful
    assert "time-sensitive" in s.score_breakdown["reasons"]["urgency"]
    # separate measures
    assert s.source_reliability == 0.8 and 0 < s.evidence_strength <= 1 and s.relevance > sigs[irrelevant.id].relevance
    assert s.verification_status == "single_source_report"
    assert not sigs[irrelevant.id].is_meaningful
    assert not sigs[old.id].is_meaningful  # older than max age
    assert s.priority_score > sigs[irrelevant.id].priority_score
    assert s.why_it_matters and s.recommended_action and s.interpretation_method == "rules"
    assert s.ai_confidence is None


def test_novelty_penalises_repeats(db, make_company):
    c = make_company(keywords=["student visa"], profile={"one_liner": "student visa"})
    src = Source(company_id=c.id, name="n", url="https://f.example", normalized_url="https://f.example", category="market", source_type="rss", approval_status="approved", credibility=0.7)
    db.add(src)
    db.flush()
    a = _item(db, c, src, "UK changes student visa rules for graduates", "x", url="https://f.example/1")
    b = _item(db, c, src, "UK changes student visa rules for graduates again", "y", url="https://f.example/2")
    s1, s2 = Analyzer(db, c).analyze([a, b])
    assert s1.novelty == 1.0 and s2.novelty < 0.5


def test_competitor_signal_polarity(db, make_company):
    from app.models import Competitor

    c = make_company(keywords=["study abroad"], profile={"one_liner": "study abroad"})
    comp = Competitor(company_id=c.id, name="Rivalco", name_key="rivalco", status="confirmed", confidence=0.9, evidence=[])
    db.add(comp)
    db.flush()
    src = Source(company_id=c.id, competitor_id=comp.id, name="Competitor news: Rivalco", url="https://x", normalized_url="https://x", category="competitors", source_type="news_search", approval_status="approved")
    db.add(src)
    db.flush()
    f = _item(db, c, src, "Rivalco raises $40 million to expand study abroad services", "Rivalco raised funding.")
    sig = Analyzer(db, c).analyze([f])[0]
    assert sig.competitor_id == comp.id and sig.signal_type == "funding" and sig.polarity == "threat"
    assert "founder-confirmed competitor" in sig.score_breakdown["reasons"]["impact"]
    assert "Rivalco" in sig.why_it_matters
    assert HIGH > 0


def test_llm_grounding_check():
    from app.services.analysis import is_grounded

    src = "Canada caps international student arrivals at 1.5 lakh a year. MeetUniversity study abroad counselling."
    assert is_grounded("Canada's cap may reduce demand for MeetUniversity counselling.", src)
    assert not is_grounded("Focus on the United States, which has the highest win rate.", src)
    assert not is_grounded("Demand may fall 30% in Canada.", src)


def test_community_post_needs_business_theme(db, make_company):
    c = make_company(keywords=["study abroad", "student visa"], profile={"one_liner": "study abroad counselling", "geographies": ["India", "United States"]})
    src = Source(company_id=c.id, name="HN", url="https://hn.algolia.com/x", normalized_url="hn", category="customers", source_type="hackernews", approval_status="approved", credibility=0.4)
    db.add(src)
    db.flush()
    job = _item(db, c, src, "Ask HN: Who wants to be hired? India, US remote", "Location: India. Remote. Willing to relocate to the United States with visa sponsorship.", url="https://news.ycombinator.com/1")
    good = _item(db, c, src, "Study abroad student visa got rejected, advice?", "My student visa for study abroad was rejected, what should I do?", url="https://news.ycombinator.com/2")
    s_job, s_good = Analyzer(db, c).analyze([job, good])
    assert s_job.verification_status == "community_claim" and not s_job.is_meaningful
    assert s_good.is_meaningful


def test_hiring_threads_are_not_customer_signals(db, make_company):
    c = make_company(keywords=["postgres", "database"], profile={"one_liner": "postgres database platform"})
    src = Source(company_id=c.id, name="HN", url="https://hn.algolia.com/y", normalized_url="hn2", category="customers", source_type="hackernews", approval_status="approved", credibility=0.4)
    db.add(src)
    db.flush()
    it = _item(db, c, src, "Comment on: Ask HN: Who wants to be hired? (November 2026)", "Skills: Postgres, database tuning, Python", url="https://news.ycombinator.com/9")
    assert not Analyzer(db, c).analyze([it])[0].is_meaningful
