"""Intelligence analysis: classify each new evidence record and score it transparently.

Priority = 100 × Σ wᵢ·componentᵢ with fixed, documented weights:
    relevance 0.30 · impact 0.25 · urgency 0.15 · source credibility 0.10 · recency 0.10 · novelty 0.10
Every component is computed by an inspectable rule and stored with a human-readable reason in
``score_breakdown``. Source reliability, evidence strength and strategic relevance are kept as separate
fields. An optional local LLM may rephrase the interpretation for top signals; it never changes the
evidence, the scores, or the verification status.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Competitor, RawItem, Signal, Source, utcnow
from app.services import nlp
from app.services.discovery import publisher_reliability
from app.services.llm import get_llm
from app.services.research import profile_text

log = logging.getLogger(__name__)

WEIGHTS = {"relevance": 0.30, "impact": 0.25, "urgency": 0.15, "credibility": 0.10, "recency": 0.10, "novelty": 0.10}
HIGH, MEDIUM = 60.0, 45.0
MEANINGFUL_RELEVANCE = 0.38
MAX_AGE_DAYS = 120

TYPE_PATTERNS = {
    "regulation": r"\b(visas?|regulat\w*|polic(y|ies)|rules?|law|legislation|bill|ministry|government|compliance|ban(s|ned)?|caps?|licen[cs]\w*|guidelines?|mandat\w*|tariffs?|tax\w*|immigration|permits?|federal|department of|home office|rbi|sebi|fca|gdpr|court)\b",
    "funding": r"\b(rais(e|es|ed|ing)|funding|series [a-f]|seed round|investment|investors?|valuation|ipo|unicorn|backed)\b",
    "acquisition": r"\b(acquir\w*|acquisition|merg(er|es|ed)|buyout|takeover|consolidat\w*)\b",
    "pricing": r"\b(pric(e|es|ing)|fees?|discounts?|cost(s|ly)?|cheaper|expensive|subscription|free tier|refund)\b",
    "product_launch": r"\b(launch\w*|unveil\w*|introduc\w*|rolls? out|new feature|releas\w*|debut\w*|beta|announc\w*)\b",
    "partnership": r"\b(partner\w*|tie[- ]up|collaborat\w*|alliance|mou|joins hands|integrat\w*)\b",
    "expansion": r"\b(expan\w*|enters?|entry into|new office|opens?|foray\w*|launches in)\b",
    "hiring": r"\b(hir(e|es|ed|ing)|appoint\w*|joins as|elevat\w*|layoffs?|job cuts|headcount|workforce|senior hires|leadership)\b",
    "technology": r"\b(ai|artificial intelligence|machine learning|genai|llm|automation|chatbot|agentic)\b",
    "economic": r"\b(inflation|rupee|currency|exchange rate|interest rates?|recession|gdp|remittances?|economy|economic|costs? of living)\b",
    "complaint": r"\b(scam|fraud|complain\w*|worst|cheated|terrible|stuck|rejected|rejection|delay\w*|frustrat\w*|denied|refused|problem|issue)\b",
    "unmet_need": r"\b(wish|looking for|is there (any|a)|need help|no option|can't find|cannot find|struggl\w*|confus\w*)\b",
    "question": r"(\?\s*$|\bhow (do|can|to|much|long)\b|\banyone\b|\badvice\b|\bshould i\b|\bwhat (are|is) the\b)",
    "review": r"\b(reviews?|ratings?|experience with)\b",
    "market_trend": r"\b(demand|trends?|surge\w*|declin\w*|drops?|growth|record|survey|report|data|enrol\w*|applications|slowdown|boom)\b",
}
CATEGORY_TYPES = {
    "customers": ["complaint", "unmet_need", "pricing", "question", "review", "regulation"],
    "competitors": ["funding", "acquisition", "pricing", "product_launch", "partnership", "expansion", "hiring", "technology", "complaint", "review"],
    "market": ["regulation", "economic", "acquisition", "funding", "technology", "market_trend", "partnership", "product_launch"],
}
DEFAULT_TYPE = {"customers": "customer_discussion", "competitors": "competitor_news", "market": "industry_news", "internal": "internal_pattern"}
TYPE_IMPACT = {
    "regulation": 0.8, "pricing": 0.75, "acquisition": 0.75, "funding": 0.65, "product_launch": 0.65, "expansion": 0.65,
    "partnership": 0.55, "economic": 0.6, "complaint": 0.6, "unmet_need": 0.6, "technology": 0.5, "hiring": 0.45,
    "market_trend": 0.55, "question": 0.4, "review": 0.45, "positioning_change": 0.6, "competitor_news": 0.4,
    "industry_news": 0.35, "customer_discussion": 0.35, "internal_pattern": 0.6,
}
AREA = {
    "regulation": "Compliance & Operations", "economic": "Finance & Pricing", "pricing": "Finance & Pricing", "funding": "Strategy",
    "acquisition": "Strategy", "product_launch": "Product", "technology": "Product", "partnership": "Partnerships & BD",
    "expansion": "Strategy", "hiring": "Talent & Org", "complaint": "Customer Experience", "unmet_need": "Product",
    "question": "Marketing & Content", "review": "Customer Experience", "market_trend": "Sales & Marketing",
    "positioning_change": "Marketing & Positioning", "competitor_news": "Strategy", "industry_news": "Strategy",
    "customer_discussion": "Customer Experience", "internal_pattern": "Sales & Marketing",
}
OWNER = {
    "Compliance & Operations": "Head of Operations / Compliance", "Finance & Pricing": "Founder / CFO", "Strategy": "Founder / CEO",
    "Product": "Head of Product", "Partnerships & BD": "Head of Partnerships", "Talent & Org": "Founder / HR lead",
    "Customer Experience": "Head of Customer Success", "Marketing & Content": "Head of Marketing", "Sales & Marketing": "Head of Growth",
    "Marketing & Positioning": "Head of Marketing",
}
URGENT_RE = re.compile(r"\b(effective (immediately|from|today)|immediately|deadline|from (january|february|march|april|may|june|july|august|september|october|november|december|next)|starting|takes effect|comes into force|new rules?|ban(s|ned)?|suspend\w*|halt\w*|crackdown|emergency|urgent|this week|cap(s|ped)?)\b", re.I)
NEGATIVE_MARKET_RE = re.compile(r"\b(ban|cap|caps|capped|restrict\w*|crackdown|tighten\w*|hike\w*|increase[sd]? fees?|declin\w*|drop\w*|fall\w*|slowdown|reject\w*|suspend\w*|cut\w*|lowest|scrutiny|curb\w*|penalt\w*)\b", re.I)
POSITIVE_MARKET_RE = re.compile(r"\b(eas(e|ed|ing)|relax\w*|scholarships?|growth|grow\w*|record|surge|boost\w*|expand\w*|new route|opportunit\w*|incentive\w*|cheaper|reduc\w* (fee|tax)|demand)\b", re.I)


def classify_type(text: str, category: str, item_type: str) -> str:
    if item_type == "page_change":
        return "pricing" if re.search(TYPE_PATTERNS["pricing"], text, re.I) else "positioning_change"
    allowed = CATEGORY_TYPES.get(category, [])
    hits = {t: len(re.findall(TYPE_PATTERNS[t], text, re.I)) for t in allowed}
    hits = {t: n for t, n in hits.items() if n}
    if not hits:
        return DEFAULT_TYPE.get(category, "industry_news")
    # order of `allowed` encodes precedence on ties
    best = max(hits.values())
    for t in allowed:
        if hits.get(t) == best:
            return t
    return DEFAULT_TYPE.get(category, "industry_news")


def verification_for(src: Source | None, item: RawItem) -> tuple[str, float]:
    """Returns (verification_status, base evidence strength). Evidence strength ≠ truth of the claim."""
    if item.item_type == "page_change":
        return "observed_change", 0.8
    if item.item_type == "internal_record":
        return "internal_document", 0.75
    dom = nlp.domain_of(item.url)
    from app.services.discovery import is_gov

    if is_gov(dom):
        return "official_primary", 0.9
    if src is not None and src.source_type in ("stackexchange", "hackernews", "reddit"):
        return "community_claim", 0.35
    if src is not None and src.credibility_label == "primary":
        return "primary_source", 0.75
    rel = publisher_reliability(item.publisher, item.url)
    return "single_source_report", 0.45 + 0.25 * (rel - 0.5) * 2


class Analyzer:
    def __init__(self, db: Session, company: Company):
        self.db = db
        self.company = company
        self.ptext = profile_text(company)
        self.emb = nlp.get_embedder()
        self.keywords = [k.lower() for k in (company.keywords or [])[:25] if len(k) > 3]
        self.competitors = list(db.scalars(select(Competitor).where(Competitor.company_id == company.id, Competitor.status != "rejected")))
        prof = company.profile or {}
        self.geos = [g for g in prof.get("geographies", []) if g]
        founder = prof.get("founder", {})
        self.priorities = " ".join(a["answer"] for k in ("growth_priorities", "risks", "market_changes", "key_decisions", "customer_problems") for a in founder.get(k, []))
        self.products = prof.get("products", [])
        since = utcnow() - timedelta(days=60)
        self.recent_titles = [t for (t,) in db.execute(select(Signal.title).where(Signal.company_id == company.id, Signal.discovered_at >= since))]

    # ------------------------------------------------------------ components
    def _relevance(self, text: str, sem: float, comp: Competitor | None, src: Source | None, prio_sim: float | None = None) -> tuple[float, str, list[str]]:
        low = text.lower()
        kw_hits = [k for k in self.keywords if k in low][:6]
        geo_hits = [g for g in self.geos if g.lower() in low or (g == "United States" and re.search(r"\b(us|u\.s\.|usa|america)\b", low)) or (g == "United Kingdom" and re.search(r"\b(uk|britain|british)\b", low))][:3]
        own = self.company.name.lower() in low or nlp.name_key(self.company.name) in nlp.name_key(low)
        kw_score = min(1.0, len(kw_hits) / 3)
        entity = 1.0 if own or comp else (0.5 if geo_hits else 0.0)
        if prio_sim is None:
            prio_sim = self.emb.similarity(self.priorities, [text[:800]])[0] if self.priorities else 0.0
        rel = 0.5 * sem + 0.2 * kw_score + 0.15 * entity + 0.15 * prio_sim
        reasons = [f"semantic match to profile {sem:.0%}"]
        if kw_hits:
            reasons.append("themes: " + ", ".join(kw_hits[:4]))
        if comp:
            reasons.append(f"mentions competitor {comp.name}")
        if own:
            reasons.append(f"mentions {self.company.name}")
        if geo_hits:
            reasons.append("markets: " + ", ".join(geo_hits))
        if prio_sim > 0.45:
            reasons.append(f"aligns with founder priorities/risks ({prio_sim:.0%})")
        return round(min(1.0, rel), 3), "; ".join(reasons), kw_hits + geo_hits

    def _impact(self, stype: str, text: str, src: Source | None, item: RawItem, comp: Competitor | None) -> tuple[float, str]:
        base = TYPE_IMPACT.get(stype, 0.4)
        reasons = [f"{stype.replace('_', ' ')} base {base:.2f}"]
        if re.search(r"(\$|₹|£|€|\brs\.?\s?\d|\d+(\.\d+)?\s?(%|percent|crore|lakh|million|billion|mn|bn))", text, re.I):
            base += 0.1
            reasons.append("+0.10 quantified (money/percent)")
        if comp is not None and comp.status == "confirmed":
            base += 0.1
            reasons.append("+0.10 founder-confirmed competitor")
        extra = item.extra or {}
        if item.item_type in ("question", "post") and ((extra.get("score") or 0) >= 5 or (extra.get("answers") or 0) >= 3 or (extra.get("points") or 0) >= 20):
            base += 0.1
            reasons.append("+0.10 high community engagement")
        if item.item_type == "page_change" and (extra.get("change_ratio") or 0) > 0.2:
            base += 0.1
            reasons.append("+0.10 substantial page change")
        return round(min(1.0, base), 3), "; ".join(reasons)

    def _recency(self, item: RawItem) -> tuple[float, int | None, str]:
        ref = item.published_at
        if ref is None:
            return 0.5, None, "publication date unknown (0.5)"
        age = max(0.0, (utcnow() - ref).total_seconds() / 86400)
        score = math.exp(-age / 21)  # ~3-week half-life-ish decay
        return round(score, 3), int(age), f"published {int(age)} days ago"

    def _urgency(self, stype: str, text: str, recency: float, age: int | None) -> tuple[float, str]:
        u = 0.2 + 0.3 * recency
        reasons = [f"recency contribution {0.3 * recency:.2f}"]
        if URGENT_RE.search(text):
            u += 0.3
            reasons.append("+0.30 time-sensitive language")
        if stype in ("regulation", "pricing"):
            u += 0.15
            reasons.append(f"+0.15 {stype} changes require timely response")
        if age is not None and age > 60:
            u -= 0.2
            reasons.append("-0.20 older than 60 days")
        return round(max(0.0, min(1.0, u)), 3), "; ".join(reasons)

    def _novelty(self, title: str, batch_titles: list[str]) -> tuple[float, str]:
        pool = self.recent_titles + batch_titles
        if not pool:
            return 1.0, "first signal of its kind"
        sims = nlp.tfidf_similarity_matrix([title], pool)[0]
        mx = float(max(sims)) if len(sims) else 0.0
        return round(max(0.0, 1 - mx), 3), f"max similarity to recent signals {mx:.0%}"

    def _polarity(self, category: str, stype: str, text: str, sent: float, comp: Competitor | None) -> str:
        if category == "competitors":
            if stype in ("complaint",) or sent < -0.4:
                return "opportunity"  # competitor weakness
            if stype in ("funding", "acquisition", "product_launch", "expansion", "partnership", "pricing", "technology", "positioning_change", "hiring"):
                return "threat"
            return "neutral"
        if category == "customers":
            return "opportunity" if stype in ("complaint", "unmet_need", "question", "pricing") else "neutral"
        neg = len(NEGATIVE_MARKET_RE.findall(text))
        pos = len(POSITIVE_MARKET_RE.findall(text))
        if neg > pos:
            return "threat"
        if pos > neg:
            return "opportunity"
        return "threat" if sent < -0.3 else ("opportunity" if sent > 0.4 else "neutral")

    # ------------------------------------------------------------ interpretation (rule-based, grounded)
    def _interpret(self, category: str, stype: str, polarity: str, comp: Competitor | None, matched: list[str], item: RawItem, src: Source | None) -> tuple[str, str]:
        name = self.company.name
        theme = matched[0] if matched else (self.keywords[0] if self.keywords else "your core market")
        product = self.products[0] if self.products else "your core offering"
        who = comp.name if comp else (item.publisher or "the source")
        if category == "competitors":
            templates = {
                "funding": (f"{who} has fresh capital, which typically funds marketing and pricing pressure in {theme}.", f"Review {name}'s differentiation versus {who} and prepare a response if {who} increases acquisition spend."),
                "acquisition": (f"{who} is consolidating capabilities, potentially widening its offering against {name}.", f"Map which of {name}'s services overlap with the combined {who} offering; brief sales on talking points."),
                "product_launch": (f"{who} launched or announced something new that may overlap with {product}.", f"Compare the new {who} offering with {product}; decide whether to match, differentiate or ignore."),
                "pricing": (f"Pricing moves by {who} directly affect {name}'s win rate on price-sensitive customers.", f"Benchmark {name}'s pricing against {who}'s change before your next sales cycle."),
                "partnership": (f"{who}'s partnership could give it distribution or supply advantages in {theme}.", f"Assess whether a comparable partnership is available to {name}."),
                "expansion": (f"{who} is expanding into new markets or segments that may overlap with {name}'s.", f"Check overlap with {name}'s target markets and adjust go-to-market priorities."),
                "hiring": (f"Leadership or team changes at {who} hint at its next strategic focus.", f"Track whether {who}'s new hires signal a push into {name}'s segments."),
                "technology": (f"{who} is adopting new technology that could raise customer expectations in {theme}.", f"Evaluate whether {name} needs an equivalent capability on its roadmap."),
                "complaint": (f"Customers are reporting problems with {who} — a potential opening for {name}.", f"Use these pain points in {name}'s messaging and target dissatisfied {who} customers."),
                "positioning_change": (f"{who} changed its website messaging/offer, signalling a positioning shift.", f"Review the added/removed text and update {name}'s competitive battlecard."),
            }
            why, act = templates.get(stype, (f"Activity by {who}, a tracked competitor of {name}, in {theme}.", f"Note in the competitor file for {who}; no immediate action unless it repeats."))
        elif category == "customers":
            templates = {
                "complaint": (f"Recurring frustration around {theme} indicates a pain point {name} can solve or must avoid.", f"Turn this pain point into content/FAQ and check whether {name}'s process has the same gap."),
                "unmet_need": (f"Customers are looking for help with {theme} that may not be well served today.", f"Validate the need with 3–5 customers and consider a targeted offer."),
                "question": (f"People repeatedly ask about {theme}; answering well builds trust and demand for {name}.", f"Publish a clear answer/guide on this question and use it in lead nurturing."),
                "pricing": (f"Cost concerns around {theme} shape purchase decisions.", f"Review how {name} communicates pricing/value for this concern."),
                "review": (f"Customer experience feedback around {theme}.", f"Share with the customer-success team."),
                "regulation": (f"Customers are confused or affected by rules around {theme}.", f"Prepare guidance content and train advisors on this rule."),
            }
            why, act = templates.get(stype, (f"Customer discussion about {theme}, a core theme for {name}.", "Monitor for recurrence before acting."))
        else:
            if polarity == "threat":
                why = f"This {stype.replace('_', ' ')} development could reduce demand or raise costs in {theme}, a core market for {name}."
                act = f"Assess exposure: which customers/pipeline does this affect, and adjust messaging or offerings within the week."
            elif polarity == "opportunity":
                why = f"This {stype.replace('_', ' ')} development may increase demand or open a new angle in {theme} for {name}."
                act = f"Decide whether to create a campaign/offer around this development while it is fresh."
            else:
                why = f"General {stype.replace('_', ' ')} context for {theme}; useful background for {name}."
                act = "No action required; keep monitoring."
        if matched:
            why += f" Connection to {name}: {', '.join(matched[:3])}."
        return why, act

    # ------------------------------------------------------------ main
    def analyze(self, items: list[RawItem]) -> list[Signal]:
        todo = [i for i in items if i.item_type != "page_snapshot"]
        if not todo:
            return []
        src_map = {s.id: s for s in self.db.scalars(select(Source).where(Source.id.in_({i.source_id for i in todo if i.source_id})))}
        texts = [f"{i.title}. {i.snippet or ''} {(i.content or '')[:600]}" for i in todo]
        sems = self.emb.similarity(self.ptext, texts)
        prio = self.emb.similarity(self.priorities, [t[:800] for t in texts]) if self.priorities else [0.0] * len(texts)
        # Novelty: one TF-IDF fit for the whole batch (recent titles + batch titles), O(n) rows instead of O(n) fits.
        titles = [i.title for i in todo]
        pool = self.recent_titles + titles
        sim_m = nlp.tfidf_similarity_matrix(titles, pool) if pool else None
        n_recent = len(self.recent_titles)
        out: list[Signal] = []
        batch_titles: list[str] = []
        by_raw: dict[int, Signal] = {}
        for idx, (item, text, sem) in enumerate(zip(todo, texts, sems)):
            src = src_map.get(item.source_id)
            category = src.category if src else "internal"
            if item.duplicate_of_id:
                orig = by_raw.get(item.duplicate_of_id) or self.db.scalars(select(Signal).where(Signal.raw_item_id == item.duplicate_of_id)).first()
                if orig:
                    orig.corroboration_count = (orig.corroboration_count or 1) + 1
                    orig.evidence_strength = round(min(1.0, orig.evidence_strength + 0.1), 3)
                    if orig.verification_status == "single_source_report":
                        orig.verification_status = "corroborated"
                    continue
            comp = None
            if src and src.competitor_id:
                comp = next((c for c in self.competitors if c.id == src.competitor_id), None)
            if comp is None:
                low = nlp.name_key(text)
                comp = next((c for c in self.competitors if len(c.name_key) > 3 and c.name_key in low), None)
                if comp and category == "market":
                    pass  # market item mentioning a competitor keeps market category but is linked
            stype = classify_type(text, category, item.item_type)
            rel, rel_why, matched = self._relevance(text, float(sem), comp, src, float(prio[idx]))
            impact, imp_why = self._impact(stype, text, src, item, comp)
            recency, age, rec_why = self._recency(item)
            urgency, urg_why = self._urgency(stype, text, recency, age)
            if sim_m is not None:
                prev = list(sim_m[idx][:n_recent]) + [sim_m[idx][n_recent + j] for j in range(idx) if titles[j] in batch_titles]
                mx = float(max(prev)) if prev else 0.0
                novelty, nov_why = (round(max(0.0, 1 - mx), 3), f"max similarity to recent signals {mx:.0%}") if prev else (1.0, "first signal of its kind")
            else:
                novelty, nov_why = self._novelty(item.title, batch_titles)
            verification, strength = verification_for(src, item)
            reliability = publisher_reliability(item.publisher, item.url) if (src and src.source_type == "news_search") else (src.credibility if src else 0.75)
            if item.published_at:
                strength += 0.05
            if len(item.snippet or "") > 120:
                strength += 0.05
            sent = nlp.sentiment(text[:1000])
            polarity = self._polarity(category, stype, text, sent, comp)
            area = AREA.get(stype, "Strategy")
            why, action = self._interpret(category, stype, polarity, comp, matched, item, src)
            comps = {"relevance": rel, "impact": impact, "urgency": urgency, "credibility": reliability, "recency": recency, "novelty": novelty}
            score = round(100 * sum(WEIGHTS[k] * comps[k] for k in WEIGHTS), 1)
            meaningful = rel >= MEANINGFUL_RELEVANCE and (age is None or age <= MAX_AGE_DAYS)
            theme_hit = any(m.lower() in [k for k in self.keywords] for m in matched) or comp is not None or self.company.name.lower() in text.lower()
            if verification == "community_claim" and re.search(r"who (wants to be hired|is hiring)|seeking freelancer|freelancer\? seeking", item.title, re.I):
                meaningful = False  # job-board threads are not customer discussions
            if verification == "community_claim" and not theme_hit:
                meaningful = False  # community chatter must match an actual business theme, not just a country name
            if item.item_type == "page_change" and not (item.extra or {}).get("added"):
                meaningful = meaningful and rel >= 0.5
            priority = "high" if score >= HIGH else ("medium" if score >= MEDIUM else "low")
            sig = Signal(
                company_id=self.company.id,
                raw_item_id=item.id,
                source_id=item.source_id,
                competitor_id=comp.id if comp else None,
                document_id=item.document_id,
                category=category,
                signal_type=stype,
                title=item.title[:1000],
                what_happened=nlp.truncate(f"{item.title}. {item.snippet or ''}", 600),
                event_date=item.published_at,
                discovered_at=item.discovered_at or utcnow(),
                evidence_url=item.url,
                evidence_snippet=nlp.truncate(item.snippet or item.content or item.title, 600),
                publisher=item.publisher,
                verification_status=verification,
                source_reliability=round(reliability, 3),
                evidence_strength=round(min(1.0, strength), 3),
                relevance=rel,
                impact=impact,
                urgency=urgency,
                novelty=novelty,
                recency=recency,
                priority_score=score,
                priority=priority,
                score_breakdown={
                    "weights": WEIGHTS,
                    "components": comps,
                    "reasons": {"relevance": rel_why, "impact": imp_why, "urgency": urg_why, "credibility": f"{'publisher' if src and src.source_type == 'news_search' else 'source'} reliability {reliability:.2f}", "recency": rec_why, "novelty": nov_why},
                    "formula": "100 × (0.30·relevance + 0.25·impact + 0.15·urgency + 0.10·credibility + 0.10·recency + 0.10·novelty)",
                    "thresholds": {"high": HIGH, "medium": MEDIUM, "meaningful_relevance": MEANINGFUL_RELEVANCE, "max_age_days": MAX_AGE_DAYS},
                    "rule_interpretation": {"why": why, "action": action},
                },
                polarity=polarity,
                business_area=area,
                sentiment=round(sent, 3),
                why_it_matters=why,
                recommended_action=action,
                is_meaningful=meaningful,
                materiality="material" if (rel >= 0.5 and impact >= 0.5) else "general",
                cluster_key=nlp.title_key(item.title)[:300],
                corroboration_count=1,
                status="new",
                interpretation_method="rules",
            )
            self.db.add(sig)
            out.append(sig)
            by_raw[item.id] = sig
            batch_titles.append(item.title)
        self.db.flush()
        return out


def analyze_items(db: Session, company: Company, items: list[RawItem]) -> list[Signal]:
    return Analyzer(db, company).analyze(items)


def is_grounded(generated: str, source: str) -> bool:
    """Reject LLM text that introduces numbers or proper names absent from the evidence/profile it was given."""
    src = source.lower()
    for num in re.findall(r"\d+(?:[.,]\d+)?", generated):
        if num not in source:
            return False
    for name in re.findall(r"\b[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*", generated):
        first = name.split()[0]
        if first in nlp.ENTITY_STOP or first.lower() in nlp.STOPWORDS or len(name) < 3:
            continue
        if name.lower() not in src and not all(w.lower() in src for w in name.split()):
            return False
    return True


def enrich_with_llm(db: Session, company: Company, limit: int = 8, since_days: int = 30) -> int:
    """Optional: let the local LLM rewrite 'why it matters' + action for the top signals, grounded on evidence.

    Scores, evidence and verification status are never modified. The rule-based interpretation is kept in
    score_breakdown['rule_interpretation'] for audit.
    """
    llm = get_llm()
    if not llm.available:
        return 0
    since = utcnow() - timedelta(days=since_days)
    sigs = list(db.scalars(select(Signal).where(Signal.company_id == company.id, Signal.is_meaningful.is_(True), Signal.interpretation_method == "rules", Signal.category != "internal", Signal.discovered_at >= since).order_by(Signal.priority_score.desc()).limit(limit)))
    prof = company.profile or {}
    founder = prof.get("founder", {})
    ctx = f"{company.name}: {prof.get('one_liner', '')} Products: {', '.join(prof.get('products', [])[:5])}. Markets: {', '.join(prof.get('geographies', [])[:6])}."
    if founder:
        ctx += " Founder priorities: " + " ".join(a["answer"][:200] for a in founder.get("growth_priorities", [])[:1])
    n = 0
    for s in sigs:
        prompt = (
            f"Company context: {ctx}\n\nEvidence ({s.publisher or 'source'}, {s.event_date.date() if s.event_date else 'date unknown'}): {s.what_happened}\n"
            f"Category: {s.category}; type: {s.signal_type}; classified as {s.polarity}.\n\n"
            "Using only the evidence and context, return JSON with keys 'why_it_matters' (max 45 words, explain the specific connection to the company) "
            "and 'recommended_action' (max 30 words, one concrete action this week). Do not add facts that are not in the evidence."
        )
        data = llm.generate_json(prompt, max_tokens=200)
        if isinstance(data, dict) and isinstance(data.get("why_it_matters"), str) and isinstance(data.get("recommended_action"), str) \
                and is_grounded(data["why_it_matters"] + " " + data["recommended_action"], f"{s.what_happened} {s.evidence_snippet or ''} {ctx} {s.title}"):
            s.why_it_matters = data["why_it_matters"].strip()[:600]
            s.recommended_action = data["recommended_action"].strip()[:400]
            s.interpretation_method = "llm"
            n += 1
    db.flush()
    return n


def reanalyze_company(db: Session, company: Company) -> dict:
    """Re-run classification/scoring over all stored evidence (e.g. after ranking rules or the profile change).

    Evidence (raw_items) is untouched; signals are rebuilt. Internal documents are re-processed from the stored files.
    """
    from pathlib import Path

    from sqlalchemy import delete

    from app.models import InternalDocument
    from app.services.internal import process_document

    db.execute(delete(Signal).where(Signal.company_id == company.id))
    db.execute(delete(RawItem).where(RawItem.company_id == company.id, RawItem.document_id.is_not(None)))
    db.flush()
    items = list(db.scalars(select(RawItem).where(RawItem.company_id == company.id).order_by(RawItem.published_at.asc().nulls_first(), RawItem.id)))
    sigs = Analyzer(db, company).analyze(items) if items else []
    n_int = 0
    for doc in db.scalars(select(InternalDocument).where(InternalDocument.company_id == company.id)):
        try:
            n_int += len(process_document(db, company, doc, Path(doc.stored_path).read_bytes()))
        except OSError:
            doc.status, doc.error = "error", "stored file missing"
    db.flush()
    return {"external_signals": len(sigs), "internal_signals": n_int, "meaningful": sum(1 for s in sigs if s.is_meaningful)}
