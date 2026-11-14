"""Monthly Signal Stack audit and business-context reassessment."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditReport, Company, ContextChange, CrawlLog, RawItem, Signal, Source, utcnow
from app.services import nlp
from app.services.discovery import discover_sources, mark_duplicates
from app.services.fetcher import PoliteFetcher, get_fetcher
from app.services.research import profile_text

log = logging.getLogger(__name__)
INACTIVE_DAYS = 45


def _source_relevance_now(company: Company, sources: list[Source], db: Session) -> dict[int, float]:
    """Current relevance of each source to the (possibly updated) profile, from its collected items or samples."""
    emb = nlp.get_embedder()
    ptext = profile_text(company)
    out = {}
    for s in sources:
        titles = [t for (t,) in db.execute(select(RawItem.title).where(RawItem.source_id == s.id).order_by(RawItem.discovered_at.desc()).limit(15))]
        if not titles:
            titles = [x.get("title", "") for x in (s.sample_items or [])] or [f"{s.name}. {s.description or ''}"]
        sims = sorted(emb.similarity(ptext, titles), reverse=True)
        top = sims[: max(3, len(sims) // 2)]
        out[s.id] = round(sum(top) / len(top), 3) if top else 0.0
    return out


def run_audit(db: Session, company: Company, trigger: str = "manual", job_run_id: int | None = None, fetcher: PoliteFetcher | None = None, discover: bool = True) -> AuditReport:
    fetcher = fetcher or get_fetcher()
    now = utcnow()
    sources = list(db.scalars(select(Source).where(Source.company_id == company.id, Source.approval_status.in_(["approved", "pending"]))))
    approved = [s for s in sources if s.approval_status == "approved"]
    # 1. availability / dead URLs
    availability = []
    for s in approved:
        if s.source_type == "reddit":
            continue
        ok, status, err = fetcher.head_ok(s.url)
        s.last_checked_at = now
        if ok:
            if s.health_status in ("dead", "failing", "unknown"):
                s.health_status = "healthy"
            s.consecutive_failures = 0
        else:
            s.consecutive_failures = (s.consecutive_failures or 0) + 1
            s.last_error = (err or "")[:1000]
            s.health_status = "dead" if status in (404, 410) else ("blocked" if err and "robots" in err else ("failing" if s.consecutive_failures >= 3 else "degraded"))
        availability.append({"source_id": s.id, "name": s.name, "ok": ok, "status": status, "error": err})
    dead = [a for a in availability if not a["ok"]]
    # 2. duplicates
    dup_pairs = mark_duplicates(db, company.id)
    # 3. inactive sources: no new items in INACTIVE_DAYS (by publication of latest item)
    inactive = []
    for s in approved:
        latest = s.last_new_item_at
        if s.source_type == "web_page":
            continue
        if latest is None or (now - latest).days > INACTIVE_DAYS:
            inactive.append({"source_id": s.id, "name": s.name, "latest_item": latest.date().isoformat() if latest else None})
    # 4. declining relevance: avg relevance of signals last 30d vs previous 30–90d, and current profile fit
    current_rel = _source_relevance_now(company, approved, db)
    declining = []
    for s in approved:
        recent = db.scalar(select(func.avg(Signal.relevance)).where(Signal.source_id == s.id, Signal.discovered_at >= now - timedelta(days=30)))
        older = db.scalar(select(func.avg(Signal.relevance)).where(Signal.source_id == s.id, Signal.discovered_at < now - timedelta(days=30), Signal.discovered_at >= now - timedelta(days=90)))
        meaningful = db.scalar(select(func.count()).select_from(Signal).where(Signal.source_id == s.id, Signal.is_meaningful.is_(True))) or 0
        total = db.scalar(select(func.count()).select_from(Signal).where(Signal.source_id == s.id)) or 0
        reason = None
        if recent is not None and older is not None and recent < older - 0.08:
            reason = f"signal relevance fell from {older:.2f} to {recent:.2f}"
        elif current_rel.get(s.id, 1) < 0.33 and s.competitor_id is None:
            reason = f"current fit to company profile only {current_rel[s.id]:.0%}"
        elif total >= 10 and meaningful / total < 0.1:
            reason = f"only {meaningful}/{total} collected items were meaningful"
        if reason:
            declining.append({"source_id": s.id, "name": s.name, "reason": reason, "current_relevance": current_rel.get(s.id)})
    # 5. new candidate sources
    new_sources = []
    discovery_summary = None
    if discover:
        discovery_summary = discover_sources(db, company, fetcher, discovered_by="audit")
        new_sources = list(db.scalars(select(Source).where(Source.company_id == company.id, Source.discovered_by == "audit", Source.approval_status == "pending", Source.created_at >= now)))
    # 6. recommendations
    remove = []
    for d in dead:
        remove.append({"source_id": d["source_id"], "name": d["name"], "why": f"Unavailable: {d['error'] or d['status']}"})
    for a, b in dup_pairs:
        s = db.get(Source, a)
        remove.append({"source_id": a, "name": s.name if s else str(a), "why": f"Duplicate of source #{b}"})
    for d in declining:
        remove.append({"source_id": d["source_id"], "name": d["name"], "why": f"Declining relevance: {d['reason']}"})
    add = [{"source_id": s.id, "name": s.name, "category": s.category, "why": s.reason, "expected_relevance": s.expected_relevance} for s in new_sources if s.recommended]
    crawl_failures = db.scalar(select(func.count()).select_from(CrawlLog).where(CrawlLog.company_id == company.id, CrawlLog.status.in_(["error", "blocked_robots"]), CrawlLog.started_at >= now - timedelta(days=30))) or 0
    content = {
        "generated_at": now.isoformat(),
        "summary": {
            "approved_sources": len(approved), "available": len(approved) - len(dead), "dead_or_unavailable": len(dead), "duplicates": len(dup_pairs),
            "inactive": len(inactive), "declining_relevance": len(declining), "new_candidates": len(new_sources), "recommended_additions": len(add),
            "recommended_removals": len(remove), "crawl_failures_30d": crawl_failures,
        },
        "availability": availability,
        "dead": dead,
        "duplicates": [{"source_id": a, "duplicate_of": b} for a, b in dup_pairs],
        "inactive": inactive,
        "declining": declining,
        "current_relevance": {str(k): v for k, v in current_rel.items()},
        "recommend_add": add,
        "recommend_remove": remove,
        "discovery": discovery_summary,
    }
    report = AuditReport(company_id=company.id, trigger=trigger, job_run_id=job_run_id, content=content, markdown=render_audit_markdown(company, content))
    db.add(report)
    db.flush()
    return report


def render_audit_markdown(company: Company, c: dict) -> str:
    s = c["summary"]
    lines = [f"# Monthly Signal Stack Audit — {company.name}", f"*Generated {c['generated_at'][:16].replace('T', ' ')} UTC*", "",
             "| Metric | Value |", "|---|---|"] + [f"| {k.replace('_', ' ').capitalize()} | {v} |" for k, v in s.items()]
    lines += ["", "## Dead / unavailable sources"] + ([f"- {d['name']} — {d['error'] or d['status']}" for d in c["dead"]] or ["- None"])
    lines += ["", "## Duplicate sources"] + ([f"- Source #{d['source_id']} duplicates #{d['duplicate_of']}" for d in c["duplicates"]] or ["- None"])
    lines += ["", f"## Inactive sources (no new items in {INACTIVE_DAYS} days)"] + ([f"- {d['name']} — latest item {d['latest_item'] or 'never'}" for d in c["inactive"]] or ["- None"])
    lines += ["", "## Declining relevance"] + ([f"- {d['name']} — {d['reason']}" for d in c["declining"]] or ["- None"])
    lines += ["", "## Recommended additions"] + ([f"- {a['name']} ({a['category']}, expected relevance {a['expected_relevance']:.0%}) — {a['why']}" for a in c["recommend_add"]] or ["- None"])
    lines += ["", "## Recommended removals"] + ([f"- {r['name']} — {r['why']}" for r in c["recommend_remove"]] or ["- None"])
    return "\n".join(lines)


CTX_STOP = {"company", "companies", "primarily", "positions", "position", "teams", "focus", "focuses", "now", "mainly", "building", "business", "customers", "users", "platform"}


def context_keyphrases(text: str | None) -> list[str]:
    """Theme phrases from a business-context statement (multi-word or domain terms; generic words dropped)."""
    if not text:
        return []
    import re as _re

    text = _re.sub(r"\([^)]*\)", " ", text)
    out = []
    for k in nlp.keyphrases([text], top_k=14):
        toks = k.split()
        if any(ch.isdigit() for ch in k) or all(t in CTX_STOP for t in toks) or (len(toks) == 1 and (toks[0] in CTX_STOP or len(toks[0]) < 4)):
            continue
        if toks[0] in CTX_STOP:
            k = " ".join(toks[1:])
        if k and k not in out:
            out.append(k)
    return out[:10]


def reassess_context(db: Session, company: Company, new_industry: str | None, new_context: str | None, fetcher: PoliteFetcher | None = None, discover: bool = True) -> ContextChange:
    """Business-context change: recompute keywords, re-score source relevance, flag sources, discover new ones."""
    from app.services.research import company_keywords  # noqa: F401

    old = {"industry": company.industry, "business_context": company.business_context, "keywords": list(company.keywords or [])}
    approved = list(db.scalars(select(Source).where(Source.company_id == company.id, Source.approval_status.in_(["approved", "pending"]))))
    before = _source_relevance_now(company, approved, db)
    if new_industry is not None:
        company.industry = new_industry or None
    if new_context is not None:
        company.business_context = new_context or None
    # Context keyphrases lead the keyword list
    ctx_kws = context_keyphrases(company.business_context)
    old_ctx_kws = set(context_keyphrases(old["business_context"]))
    base = [k for k in old["keywords"] if k not in ctx_kws and k not in old_ctx_kws]  # themes from the previous context are retired
    company.keywords = (ctx_kws + base)[:30]
    profile = dict(company.profile or {})
    if new_industry:
        profile["industry"] = new_industry
    profile["business_context"] = company.business_context
    company.profile = profile
    company.profile_version = (company.profile_version or 0) + 1
    db.flush()
    after = _source_relevance_now(company, approved, db)
    changes, flagged = [], []
    for s in approved:
        b, a = before.get(s.id, 0), after.get(s.id, 0)
        s.expected_relevance = a
        changes.append({"source_id": s.id, "name": s.name, "before": b, "after": a, "delta": round(a - b, 3)})
        if s.approval_status == "approved" and a < 0.33 and a < b - 0.02 and s.competitor_id is None:
            flagged.append({"source_id": s.id, "name": s.name, "why": f"Relevance to new context {a:.0%} (was {b:.0%}) — no longer useful"})
            s.recommended = False
            s.relevance_rationale = f"Context change: relevance now {a:.0%} (was {b:.0%}); recommended for removal."
    new_ids = []
    if discover:
        disc = discover_sources(db, company, fetcher, discovered_by="context_change")
        new_ids = [s.id for s in db.scalars(select(Source).where(Source.company_id == company.id, Source.discovered_by == "context_change"))]
    changes.sort(key=lambda c: c["delta"])
    added_kw = [k for k in company.keywords if k not in old["keywords"]]
    removed_kw = [k for k in old["keywords"] if k not in company.keywords]
    summary = (f"Business context updated. {len(added_kw)} new themes ({', '.join(added_kw[:5]) or 'none'}) now lead source discovery. "
               f"Relevance was re-scored for {len(approved)} sources: {sum(1 for c in changes if c['delta'] > 0.03)} gained, {sum(1 for c in changes if c['delta'] < -0.03)} lost relevance; "
               f"{len(flagged)} flagged as no longer useful; {len(new_ids)} new sources proposed.")
    cc = ContextChange(company_id=company.id, old_context=old, new_context={"industry": company.industry, "business_context": company.business_context, "keywords": company.keywords},
                       added_keywords=added_kw, removed_keywords=removed_kw, relevance_changes=changes, flagged_sources=flagged, new_source_ids=new_ids, summary=summary)
    db.add(cc)
    db.flush()
    return cc
