"""Adaptive founder interview.

Ten primary questions are generated per company from its research (products, segments, markets,
discovered competitors, public developments, gaps that need confirmation). A local LLM may phrase them;
otherwise grounded rule-based builders are used. Each question records *why* it was asked.
Answers update the structured profile; follow-ups are generated only when an answer warrants it and are
de-duplicated against every question already asked.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Company, Competitor, FactStatus, InterviewQuestion, ProfileFact, utcnow
from app.services import nlp
from app.services.llm import get_llm

log = logging.getLogger(__name__)

TOPICS = [
    "revenue_streams",
    "high_value_customers",
    "customer_problems",
    "differentiation",
    "competitors",
    "market_changes",
    "risks",
    "growth_priorities",
    "internal_data",
    "decisions",
]
TOPIC_FIELD = {
    "revenue_streams": "revenue_streams",
    "high_value_customers": "high_value_segments",
    "customer_problems": "customer_problems",
    "differentiation": "differentiators",
    "competitors": "competitor_notes",
    "market_changes": "market_changes",
    "risks": "risks",
    "growth_priorities": "growth_priorities",
    "internal_data": "internal_data_sources",
    "decisions": "key_decisions",
}
TOPIC_LABEL = {
    "revenue_streams": "Revenue streams",
    "high_value_customers": "High-value customers",
    "customer_problems": "Customer problems",
    "differentiation": "Competitive advantage",
    "competitors": "Competitors & substitutes",
    "market_changes": "Market changes",
    "risks": "Business risks",
    "growth_priorities": "Growth priorities",
    "internal_data": "Internal intelligence",
    "decisions": "Decisions to support",
}
MAX_FOLLOWUPS = 5


def _join(items: list[str], n: int = 3) -> str:
    items = [i for i in items if i][:n]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def build_context(db: Session, company: Company) -> dict:
    p = company.profile or {}
    comps = list(db.scalars(select(Competitor).where(Competitor.company_id == company.id, Competitor.status != "rejected").order_by(Competitor.confidence.desc())))
    devs = list(db.scalars(select(ProfileFact).where(ProfileFact.company_id == company.id, ProfileFact.field == "developments", ProfileFact.status == "unverified")))
    return {
        "name": company.name,
        "industry": company.industry or p.get("industry") or "your industry",
        "products": [x for x in p.get("products", []) if len(x) < 60][:5],
        "segments": [s for s in p.get("customer_segments", [])][:4],
        "geos": [g for g in p.get("geographies", []) if g != "India" or len(p.get("geographies", [])) == 1][:5],
        "all_geos": p.get("geographies", []),
        "business_model": p.get("business_model", []),
        "competitors": [c.name for c in comps][:4],
        "developments": [d.value for d in devs][:2],
        "keywords": (company.keywords or [])[:8],
        "has_pricing": any("pricing" in (u or "") for u in (company.research_summary or {}).get("pages_crawled", [])),
        "context": company.business_context or "",
    }


# ---------------------------------------------------------------- rule-based, research-grounded builders
def _q_revenue(c):
    if c["products"]:
        q = f"Your website presents {_join(c['products'], 3)}. Which of these actually generate revenue for {c['name']}, and roughly how is revenue split between them?"
        why = f"Research found these offerings on the website but no public revenue breakdown ({'no' if not c['has_pricing'] else 'a'} public pricing page)."
    else:
        q = f"What are {c['name']}'s main revenue streams today, and which one is growing fastest?"
        why = "Research could not identify distinct product lines from the website."
    if c["business_model"]:
        q += f" (We inferred a possible {c['business_model'][0].lower()} model — is that right?)"
        why += f" Business model '{c['business_model'][0]}' is only an inference from wording."
    return q, why


def _q_customers(c):
    if len(c["segments"]) >= 2:
        q = f"The website speaks to {_join([s.lower() for s in c['segments']], 3)}. Which of these is your highest-value customer segment, and what does a typical high-value customer look like?"
        why = f"Website addresses several segments ({_join(c['segments'], 4)}); their relative value is not public."
    elif c["segments"]:
        q = f"Within {c['segments'][0].lower()}, which sub-group brings the most value to {c['name']} (by revenue, margin or lifetime value)?"
        why = f"Only one segment ({c['segments'][0]}) is evident from the website."
    else:
        q = f"Who exactly buys from {c['name']}, and which customer type is most valuable?"
        why = "No clear customer segment language was found on the website."
    return q, why


def _q_problems(c):
    focus = c["keywords"][0] if c["keywords"] else c["industry"]
    q = f"What are the most painful problems your customers face around {focus} before they come to {c['name']}, and what do they complain about most during the process?"
    why = f"Customer-problem monitoring will search for these exact pain points; '{focus}' is the strongest theme on the website."
    return q, why


def _q_diff(c):
    if c["competitors"]:
        q = f"When a customer compares {c['name']} with alternatives like {_join(c['competitors'], 2)}, why do they choose you — and when do you lose?"
        why = f"Discovery found {_join(c['competitors'], 4)} in related news coverage; your positioning against them is not public."
    else:
        q = f"Why do customers choose {c['name']} over the alternatives they consider, and in which situations do you typically lose deals?"
        why = "Positioning claims on the website need founder validation."
    return q, why


def _q_competitors(c):
    if c["competitors"]:
        q = f"Our research surfaced {_join(c['competitors'], 4)} as possible competitors. Which of these really compete with you, which are irrelevant, and who is missing (including substitutes such as doing it yourself)?"
        why = "Competitor list was discovered automatically from news co-mentions and must be validated."
    else:
        q = f"Which companies or substitutes do you lose customers to most often in {c['industry']}?"
        why = "Automatic discovery found too little public evidence to name competitors confidently."
    return q, why


def _q_market(c):
    if c["geos"]:
        q = f"Which regulatory, economic or industry changes in {_join(c['geos'], 3)} would most change demand for {c['name']} over the next year?"
        why = f"The website references these markets: {_join(c['all_geos'], 6)}."
    else:
        q = f"Which industry, regulatory or technology shifts in {c['industry']} are you watching most closely right now?"
        why = "No explicit geographic markets were found on the website."
    return q, why


def _q_risks(c):
    if c["developments"]:
        q = f"Public coverage mentions: “{c['developments'][0][:120]}”. Beyond this, what developments could materially hurt {c['name']} in the next 6–12 months?"
        why = "Research found third-party coverage of the company that may indicate exposure."
    else:
        q = f"What single development (a competitor move, policy change, platform shift or cost increase) would hurt {c['name']} most if it happened next quarter?"
        why = "No public developments about the company were found, so risk exposure must come from the founder."
    return q, why


def _q_growth(c):
    if c["products"] and c["geos"]:
        q = f"Over the next 6–12 months, is growth expected to come from new markets (e.g. beyond {_join(c['geos'], 2)}), new offerings beyond {c['products'][0]}, or deeper penetration of existing customers?"
    else:
        q = f"What are {c['name']}'s top two growth priorities for the next 6–12 months, and what would success look like?"
    why = "Growth priorities determine which market and competitor developments are material."
    return q, why


def _q_internal(c):
    q = f"Which internal information could you share to sharpen this intelligence — e.g. CRM exports, lost-deal reasons, support tickets, sales-call notes or customer feedback for {c['name']}? What format are they in?"
    why = "Internal Intelligence category supports CSV, XLSX, PDF and TXT uploads."
    return q, why


def _q_decisions(c):
    q = f"Which decisions in the coming quarter should this intelligence help you make — for example pricing, market entry, hiring, partnerships or product bets for {c['name']}?"
    why = "Recommended actions in the Monday Brief are tied to the founder's stated decisions."
    return q, why


BUILDERS = {
    "revenue_streams": _q_revenue,
    "high_value_customers": _q_customers,
    "customer_problems": _q_problems,
    "differentiation": _q_diff,
    "competitors": _q_competitors,
    "market_changes": _q_market,
    "risks": _q_risks,
    "growth_priorities": _q_growth,
    "internal_data": _q_internal,
    "decisions": _q_decisions,
}


def _llm_questions(ctx: dict) -> dict[str, str] | None:
    llm = get_llm()
    if not llm.available:
        return None
    prompt = (
        "You are preparing a founder interview for a business-intelligence system. Using ONLY the research context, write exactly one "
        "specific question for each topic key. Each question must reference concrete details from the context (products, segments, markets, "
        "named competitors) when available, be one or two sentences, and end with '?'. Do not invent facts.\n\n"
        f"Research context: {ctx}\n\nTopics: {TOPICS}\n\nReturn JSON object mapping each topic key to its question."
    )
    data = llm.generate_json(prompt, max_tokens=900)
    if not isinstance(data, dict):
        return None
    out = {}
    for t in TOPICS:
        q = data.get(t)
        if isinstance(q, str) and q.strip().endswith("?") and 30 <= len(q) <= 400:
            out[t] = q.strip()
    return out


def generate_questions(db: Session, company: Company, use_llm: bool = True) -> list[InterviewQuestion]:
    """(Re)generate the 10 primary questions. Existing answers are preserved per topic."""
    ctx = build_context(db, company)
    existing = {q.topic: q for q in db.scalars(select(InterviewQuestion).where(InterviewQuestion.company_id == company.id, InterviewQuestion.is_followup.is_(False)))}
    llm_qs = _llm_questions(ctx) if use_llm else None
    specifics = [s.lower() for s in ctx["products"] + ctx["segments"] + ctx["geos"] + ctx["competitors"] if s and len(s) > 2]
    out = []
    for i, topic in enumerate(TOPICS, start=1):
        rule_q, why = BUILDERS[topic](ctx)
        text, by = rule_q, "rules"
        # Accept LLM phrasing only if it is concise and grounded in at least one researched specific
        # (product, segment, market or competitor) — otherwise keep the research-grounded rule question.
        if llm_qs and topic in llm_qs and len(llm_qs[topic].split()) <= 45 and any(s in llm_qs[topic].lower() for s in specifics):
            text, by = llm_qs[topic], "llm"
        q = existing.get(topic)
        if q is None:
            q = InterviewQuestion(company_id=company.id, position=i, sort_key=float(i), topic=topic, status="pending", is_followup=False)
            db.add(q)
        if q.status in (None, "pending"):
            q.question, q.generated_by, q.rationale = text, by, why
        out.append(q)
    company.status = "interviewing" if company.status in ("researched", "created") else company.status
    db.flush()
    return out


def ordered_questions(db: Session, company_id: int) -> list[InterviewQuestion]:
    return list(db.scalars(select(InterviewQuestion).where(InterviewQuestion.company_id == company_id).order_by(InterviewQuestion.sort_key)))


def next_question(db: Session, company_id: int) -> InterviewQuestion | None:
    return db.scalar(select(InterviewQuestion).where(InterviewQuestion.company_id == company_id, InterviewQuestion.status == "pending").order_by(InterviewQuestion.sort_key).limit(1))


# ---------------------------------------------------------------- answers -> profile
COMPANY_NAME_RE = re.compile(r"\b([A-Z][a-zA-Z0-9&]+(?:\s(?:[A-Z][a-zA-Z0-9&]+|Edu|AI|Pay))*)\b")


def _apply_answer_to_profile(db: Session, company: Company, q: InterviewQuestion) -> dict:
    tag = f"interview:{q.id}"
    db.execute(delete(ProfileFact).where(ProfileFact.company_id == company.id, ProfileFact.source_url == tag))
    changes: dict = {"facts": [], "competitors_added": [], "keywords_added": []}
    field = TOPIC_FIELD.get(q.topic, q.topic)
    if q.status == "skipped":
        db.add(ProfileFact(company_id=company.id, field=field, value=f"Founder skipped: {TOPIC_LABEL.get(q.topic, q.topic)} (confidential)", status=FactStatus.needs_confirmation.value, origin="interview", source_url=tag))
        return changes
    ans = nlp.clean_text(q.answer)
    if not ans:
        return changes
    by = q.answered_by or "founder"
    if by == "founder":
        status, evidence = FactStatus.verified.value, f"Founder answer to: {q.question[:300]}"
    else:
        label = "team member" if by == "team_member" else "demo operator (NOT the founder — simulated input for demonstration)"
        status, evidence = FactStatus.assumption.value, f"Answered by {label} to: {q.question[:250]}"
    db.add(ProfileFact(company_id=company.id, field=field, value=ans[:2000], status=status, origin="interview", source_url=tag, evidence=evidence))
    changes["facts"].append(field)
    profile = dict(company.profile or {})
    founder = dict(profile.get("founder", {}))
    founder[field] = (founder.get(field, []) if isinstance(founder.get(field), list) else [])
    founder[field] = [a for a in founder[field] if a.get("q") != q.id] + [{"q": q.id, "answer": ans[:600]}]
    profile["founder"] = founder
    # Competitors named by the founder become confirmed competitors.
    if q.topic in ("competitors", "differentiation") and (q.answered_by or "founder") == "founder":
        from app.services.competitors import add_founder_competitor

        known = {c.name_key: c for c in db.scalars(select(Competitor).where(Competitor.company_id == company.id))}
        for m in COMPANY_NAME_RE.finditer(q.answer or ""):
            name = m.group(1).strip()
            key = nlp.name_key(name)
            if key == nlp.name_key(company.name) or len(key) < 3 or name.split()[0] in nlp.ENTITY_STOP or re.match(r"^(We|They|Our|Their|Most|Some|Many|Students|Customers|It|If|When|Also|Both|None|Yes|No)$", name):
                continue
            if key in known or q.topic == "competitors":
                comp = add_founder_competitor(db, company, name, f"Named by {q.answered_by or 'founder'} in interview ({TOPIC_LABEL[q.topic]}).")
                changes["competitors_added"].append(comp.name)
        # explicit rejections: "X is irrelevant/not a competitor"
        for key, comp in known.items():
            pat = re.compile(re.escape(comp.name) + r"[^.]{0,40}\b(irrelevant|not (a )?competitor|don'?t compete|not relevant)", re.I)
            if pat.search(q.answer or ""):
                comp.status = "rejected"
                changes.setdefault("competitors_rejected", []).append(comp.name)
    # Geographies mentioned
    geos = nlp.find_countries(ans)
    if geos:
        profile["geographies"] = list(dict.fromkeys((profile.get("geographies") or []) + list(geos)))
    # Keywords from substantive answers feed source discovery.
    if q.topic in ("customer_problems", "market_changes", "risks", "growth_priorities", "high_value_customers", "revenue_streams"):
        new_kws = [k for k in nlp.keyphrases([ans], top_k=4) if len(k) > 3 and not any(ch.isdigit() for ch in k)]
        kws = list(company.keywords or [])
        for k in new_kws:
            if k not in kws:
                kws.insert(min(len(kws), 10), k)
                changes["keywords_added"].append(k)
        company.keywords = kws[:40]
    company.profile = profile
    company.profile_version = (company.profile_version or 0) + 1
    return changes


# ---------------------------------------------------------------- follow-ups
def _is_duplicate(db: Session, company_id: int, text: str) -> bool:
    existing = [q.question for q in ordered_questions(db, company_id)]
    if not existing:
        return False
    sims = nlp.tfidf_similarity_matrix([text], existing)[0]
    return bool(max(sims) > 0.55)


def _rule_followup(company: Company, q: InterviewQuestion, ans: str) -> tuple[str, str] | None:
    words = len(ans.split())
    if words < 8:
        probes = {
            "revenue_streams": "Could you give a rough percentage split between those revenue streams, and which has the best margin?",
            "high_value_customers": "What makes that customer segment more valuable — deal size, conversion rate, or retention?",
            "customer_problems": "Can you share an example of how a customer described that problem in their own words?",
            "differentiation": "Which deals did you lose recently, and what reason did the customer give?",
            "competitors": "Which of those competitors worries you most right now, and why?",
            "market_changes": "Which specific policy, price or technology change would you want an alert on the same day it happens?",
            "risks": "What early warning sign would tell you that this risk is starting to materialise?",
            "growth_priorities": "What has to be true in the market for that growth priority to succeed?",
            "internal_data": "Which of those internal sources is updated most often and could be exported weekly?",
            "decisions": "What information is missing today that makes that decision hard?",
        }
        return probes.get(q.topic), "Answer was brief; a targeted probe captures detail the ranking engine needs."
    if q.topic == "competitors":
        names = [m.group(1) for m in COMPANY_NAME_RE.finditer(ans) if nlp.name_key(m.group(1)) != nlp.name_key(company.name) and m.group(1).split()[0] not in nlp.ENTITY_STOP]
        if names:
            return (f"What do customers find attractive about {names[0]} compared with {company.name} — price, brand, speed or something else?", f"Founder named {names[0]}; understanding its pull helps judge which competitor moves matter.")
    if q.topic == "customer_problems":
        return (f"Where do customers usually voice these problems — online forums, reviews, social media, sales calls or support tickets?", "Identifies where customer-signal sources should be monitored.")
    if q.topic == "growth_priorities":
        geos = nlp.find_countries(ans)
        if geos:
            g = list(geos)[0]
            return (f"For {g}, which regulatory or competitive developments would change your plans there?", f"Founder mentioned {g}; market sources for it should be prioritised.")
    if q.topic == "risks":
        return ("If that risk started to materialise, what would be the first signal you would expect to see in the news or from customers?", "Defines early-warning items for the 'What We Should Watch' section.")
    return None


def _llm_followup(company: Company, q: InterviewQuestion, ans: str, history: list[str]) -> str | None:
    llm = get_llm()
    if not llm.available:
        return None
    prompt = (
        f"Founder interview for {company.name}.\nPrevious questions already asked:\n- " + "\n- ".join(history[-12:]) +
        f"\n\nLatest question: {q.question}\nFounder answer: {ans}\n\n"
        "If the answer leaves an important specific gap relevant to monitoring competitors, customers or market changes, write ONE short "
        "follow-up question that does not repeat any previous question. Otherwise reply NONE. Reply with only the question or NONE."
    )
    out = llm.generate(prompt, max_tokens=70, temperature=0.2)
    if not out or "NONE" in out.upper()[:8] or not out.strip().endswith("?"):
        return None
    return out.strip().strip('"')


def answer_question(db: Session, company: Company, q: InterviewQuestion, answer: str | None, skip: bool = False, confidential: bool = False, allow_followup: bool = True, use_llm: bool = True, answered_by: str = "founder") -> dict:
    was_answered = q.status != "pending"
    q.answered_by = answered_by
    if skip:
        q.status, q.answer, q.confidential = "skipped", None, True
    else:
        q.status, q.answer = "answered", (answer or "").strip()
    q.answered_at = utcnow()
    changes = _apply_answer_to_profile(db, company, q)
    followup = None
    if allow_followup and not skip and not q.is_followup and not was_answered:
        n_follow = db.scalar(select(func.count()).select_from(InterviewQuestion).where(InterviewQuestion.company_id == company.id, InterviewQuestion.is_followup.is_(True))) or 0
        has_child = db.scalar(select(func.count()).select_from(InterviewQuestion).where(InterviewQuestion.parent_id == q.id)) or 0
        if n_follow < MAX_FOLLOWUPS and not has_child:
            text, why, by = None, None, "rules"
            history = [x.question for x in ordered_questions(db, company.id)]
            if use_llm and len((answer or "").split()) >= 8:
                text = _llm_followup(company, q, answer or "", history)
                if text:
                    why, by = "Generated by local LLM from the founder's answer to close a specific gap.", "llm"
            if not text:
                rf = _rule_followup(company, q, answer or "")
                if rf and rf[0]:
                    text, why = rf
            if text and not _is_duplicate(db, company.id, text):
                followup = InterviewQuestion(company_id=company.id, position=q.position, sort_key=q.sort_key + 0.5, topic=q.topic, question=text, rationale=why, is_followup=True, parent_id=q.id, generated_by=by, status="pending", confidential=False)
                db.add(followup)
    remaining = db.scalar(select(func.count()).select_from(InterviewQuestion).where(InterviewQuestion.company_id == company.id, InterviewQuestion.status == "pending")) or 0
    if remaining == 0 and followup is None:
        company.status = "configured" if company.status == "interviewing" else company.status
    db.flush()
    return {"changes": changes, "followup_id": followup.id if followup else None}
