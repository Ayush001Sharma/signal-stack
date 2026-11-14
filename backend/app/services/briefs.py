"""Monday Morning Intelligence Brief generation (JSON content + Markdown + HTML/PDF export).

Sections (fixed order): 1 Executive Summary · 2 Customer Signals · 3 Competitor Intelligence ·
4 Market Intelligence · 5 Internal Business Intelligence · 6 Opportunities Identified · 7 Risks & Threats ·
8 Recommended Actions for This Week · 9 What We Should Watch · 10 Source Appendix.

Only stored, evidence-backed signals are used. Empty sections say so explicitly — nothing is invented.
"""
from __future__ import annotations

import html
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Brief, BriefAction, Company, Competitor, CrawlRun, InternalDocument, InterviewQuestion, Signal, Source, utcnow
from app.services import nlp
from app.services.analysis import OWNER
from app.services.llm import get_llm

log = logging.getLogger(__name__)

VERIFICATION_LABEL = {
    "official_primary": "Verified — official primary source",
    "primary_source": "Primary source (self-published by the organisation)",
    "corroborated": "Corroborated by multiple publishers",
    "single_source_report": "Reported by a single publisher (unconfirmed)",
    "community_claim": "Community post — anecdotal, unverified",
    "observed_change": "Directly observed page change",
    "internal_document": "Internal company data (uploaded)",
}


def is_synthetic(doc) -> bool:
    text = f"{doc.filename} {doc.description or ''}".lower()
    return "synthetic" in text


def _period_signals(db: Session, company: Company, start: datetime, end: datetime) -> list[Signal]:
    q = select(Signal).where(
        Signal.company_id == company.id,
        Signal.is_meaningful.is_(True),
        Signal.status != "dismissed",
        or_(
            and_(Signal.event_date.is_not(None), Signal.event_date >= start, Signal.event_date <= end),
            and_(Signal.event_date.is_(None), Signal.discovered_at >= start, Signal.discovered_at <= end),
        ),
    ).order_by(Signal.priority_score.desc())
    sigs = list(db.scalars(q))
    # collapse near-duplicate stories (same cluster key) keeping the highest-scoring one
    seen, out = set(), []
    for s in sigs:
        key = s.cluster_key or s.title
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


class Refs:
    def __init__(self):
        self.ids: dict[int, int] = {}
        self.sigs: list[Signal] = []

    def ref(self, s: Signal) -> str:
        if s.id not in self.ids:
            self.ids[s.id] = len(self.ids) + 1
            self.sigs.append(s)
        return f"S{self.ids[s.id]}"


def _sig_dict(s: Signal, refs: Refs, comp_names: dict[int, str]) -> dict:
    return {
        "ref": refs.ref(s),
        "signal_id": s.id,
        "title": s.title,
        "category": s.category,
        "type": s.signal_type,
        "what_happened": s.what_happened,
        "when": s.event_date.date().isoformat() if s.event_date else None,
        "discovered": s.discovered_at.date().isoformat() if s.discovered_at else None,
        "publisher": s.publisher,
        "evidence_url": s.evidence_url,
        "evidence": s.evidence_snippet,
        "verification": VERIFICATION_LABEL.get(s.verification_status, s.verification_status),
        "source_reliability": s.source_reliability,
        "evidence_strength": s.evidence_strength,
        "relevance": s.relevance,
        "impact": s.impact,
        "urgency": s.urgency,
        "priority": s.priority,
        "priority_score": s.priority_score,
        "polarity": s.polarity,
        "business_area": s.business_area,
        "why_it_matters": s.why_it_matters,
        "recommended_action": s.recommended_action,
        "interpretation": "AI-assisted interpretation (local LLM)" if s.interpretation_method == "llm" else "Rule-based interpretation",
        "competitor": comp_names.get(s.competitor_id) if s.competitor_id else None,
        "materiality": s.materiality,
        "score_reasons": (s.score_breakdown or {}).get("reasons", {}),
    }


def generate_brief(db: Session, company: Company, trigger: str = "manual", lookback_days: int | None = None, job_run_id: int | None = None, use_llm: bool = True) -> Brief:
    lookback = lookback_days or (company.schedule.brief_lookback_days if company.schedule else 14)
    end = utcnow()
    start = end - timedelta(days=lookback)
    sigs = _period_signals(db, company, start, end)
    comp_names = {c.id: c.name for c in db.scalars(select(Competitor).where(Competitor.company_id == company.id))}
    refs = Refs()
    by_cat: dict[str, list[Signal]] = defaultdict(list)
    for s in sigs:
        by_cat[s.category].append(s)

    docs_all = list(db.scalars(select(InternalDocument).where(InternalDocument.company_id == company.id, InternalDocument.status == "processed")))
    synth_ids = {d.id for d in docs_all if is_synthetic(d)}
    sigs = [s for s in sigs if not (s.category == "internal" and s.document_id in synth_ids)]
    by_cat = defaultdict(list)
    for s in sigs:
        by_cat[s.category].append(s)
    # 1. Executive summary: top 5 with category diversity (max 3 per category; community anecdotes need ≥ medium priority)
    exec_items, per_cat = [], Counter()
    for s in sigs:
        if per_cat[s.category] >= 3 or (s.verification_status == "community_claim" and s.priority == "low"):
            continue
        exec_items.append(s)
        per_cat[s.category] += 1
        if len(exec_items) == 5:
            break
    if len(exec_items) < 5:
        for s in sigs:
            if s not in exec_items:
                exec_items.append(s)
            if len(exec_items) == 5:
                break

    # 2. Customer signals
    cust = by_cat.get("customers", [])[:8]
    cust_types = Counter(s.signal_type for s in by_cat.get("customers", []))
    avg_sent = round(sum((s.sentiment or 0) for s in by_cat.get("customers", [])) / max(1, len(by_cat.get("customers", []))), 2) if by_cat.get("customers") else None

    # 3. Competitors grouped
    comp_groups: dict[str, list[Signal]] = defaultdict(list)
    for s in by_cat.get("competitors", []):
        comp_groups[comp_names.get(s.competitor_id, "Other competitor activity")].append(s)

    # 4. Market: material vs general
    market = by_cat.get("market", [])
    material = [s for s in market if s.materiality == "material"][:6]
    general = [s for s in market if s.materiality != "material"][:5]

    # 5. Internal (signals from uploads are not date-bound to the window; use latest per document)
    internal = list(db.scalars(select(Signal).where(Signal.company_id == company.id, Signal.category == "internal", Signal.status != "dismissed").order_by(Signal.priority_score.desc()).limit(8)))
    docs = list(db.scalars(select(InternalDocument).where(InternalDocument.company_id == company.id, InternalDocument.status == "processed")))

    synthetic_docs = {d.id for d in docs if is_synthetic(d)}
    internal_real = [s for s in internal if s.document_id not in synthetic_docs]
    sigs = [s for s in sigs if not (s.category == "internal" and s.document_id in synthetic_docs)]
    pool = sigs + [s for s in internal_real if s not in sigs]
    opps = sorted([s for s in pool if s.polarity == "opportunity"], key=lambda s: -s.priority_score)[:6]
    risks = sorted([s for s in pool if s.polarity == "threat"], key=lambda s: -s.priority_score)[:6]

    # 8. Actions — from the highest-priority opportunities, risks and exec items; de-duplicated
    actions, seen_actions = [], set()
    for s in sorted(set(exec_items + opps[:3] + risks[:3]), key=lambda s: -s.priority_score):
        a = (s.recommended_action or "").strip()
        if not a or a in seen_actions or a.startswith("No action"):
            continue
        seen_actions.add(a)
        actions.append({"action": a, "reason": f"[{refs.ref(s)}] {s.title[:140]}", "owner": OWNER.get(s.business_area, "Founder / CEO"), "priority": s.priority, "signal_id": s.id})
        if len(actions) >= 7:
            break

    # 9. Watch list: weak-evidence or early signals + founder-stated risks without evidence
    watch = []
    for s in sigs:
        if s in exec_items:
            continue
        if s.verification_status in ("community_claim", "single_source_report") and s.evidence_strength < 0.6 and s.relevance >= 0.45:
            watch.append({"title": s.title, "why": f"Early/unconfirmed ({VERIFICATION_LABEL.get(s.verification_status)}); relevance {s.relevance:.0%}. Confirm before acting.", "ref": refs.ref(s), "url": s.evidence_url})
        if len(watch) >= 6:
            break
    founder = (company.profile or {}).get("founder", {})
    by_q = {q.id: (q.answered_by or "founder") for q in db.scalars(select(InterviewQuestion).where(InterviewQuestion.company_id == company.id))}
    for r in founder.get("risks", [])[:2]:
        who = by_q.get(r.get("q"), "founder")
        label = "Founder-stated risk" if who == "founder" else ("Team-stated risk" if who == "team_member" else "Interview risk (demo operator input, not the founder)")
        watch.append({"title": f"{label}: {nlp.truncate(r['answer'], 140)}", "why": "Raised in the interview; keep monitoring for corroborating evidence.", "ref": None, "url": None})
    unhealthy = list(db.scalars(select(Source).where(Source.company_id == company.id, Source.approval_status == "approved", Source.health_status.in_(["failing", "dead", "blocked"]))))
    for src in unhealthy[:3]:
        watch.append({"title": f"Source health: {src.name} is {src.health_status}", "why": f"Coverage gap until fixed: {nlp.truncate(src.last_error or '', 120)}", "ref": None, "url": src.url})

    ctx = {
        "executive_summary": [_sig_dict(s, refs, comp_names) for s in exec_items],
        "customer_signals": {
            "items": [_sig_dict(s, refs, comp_names) for s in cust],
            "themes": [{"type": t, "count": n} for t, n in cust_types.most_common()],
            "average_sentiment": avg_sent,
            "empty_message": None if cust else "No meaningful customer signals were collected in this period. No customer feedback has been inferred or synthesised.",
        },
        "competitor_intelligence": {
            "groups": [{"competitor": k, "items": [_sig_dict(s, refs, comp_names) for s in v[:4]]} for k, v in sorted(comp_groups.items(), key=lambda kv: -max(x.priority_score for x in kv[1]))],
            "empty_message": None if comp_groups else "No meaningful competitor developments were detected in this period.",
        },
        "market_intelligence": {
            "material": [_sig_dict(s, refs, comp_names) for s in material],
            "general": [_sig_dict(s, refs, comp_names) for s in general],
            "empty_message": None if market else "No meaningful market, regulatory or economic developments were detected in this period.",
        },
        "internal_intelligence": {
            "items": [_sig_dict(s, refs, comp_names) for s in internal],
            "documents": [{"id": d.id, "filename": d.filename, "records": d.record_count, "uploaded": d.uploaded_at.date().isoformat(), "description": d.description, "synthetic": is_synthetic(d)} for d in docs],
            "synthetic_note": "Items from documents marked SYNTHETIC are test data used to demonstrate the pipeline. They are shown only in this section and excluded from the executive summary, opportunities, risks and actions." if synthetic_docs else None,
            "empty_message": None if internal else "No internal documents have been uploaded, so no internal intelligence is available. Upload CRM exports, call notes or support logs to enable this section.",
        },
        "opportunities": [{**_sig_dict(s, refs, comp_names), "next_step": s.recommended_action} for s in opps],
        "opportunities_note": None if len(opps) >= 3 else f"Only {len(opps)} opportunit{'y is' if len(opps) == 1 else 'ies are'} supported by collected evidence this period; no further opportunities were invented.",
        "risks": [_sig_dict(s, refs, comp_names) for s in risks],
        "risks_note": None if risks else "No evidence-backed risks or threats were detected this period.",
        "recommended_actions": actions,
        "watch_list": watch,
    }
    appendix = []
    for s in refs.sigs:
        appendix.append({
            "ref": f"S{refs.ids[s.id]}", "title": s.title, "source": s.publisher, "url": s.evidence_url, "published": s.event_date.date().isoformat() if s.event_date else "unknown",
            "discovered": s.discovered_at.date().isoformat() if s.discovered_at else None, "snippet": s.evidence_snippet, "verification": VERIFICATION_LABEL.get(s.verification_status, s.verification_status),
            "source_reliability": s.source_reliability, "evidence_strength": s.evidence_strength, "strategic_relevance": s.relevance, "interpretation": "AI-assisted (local LLM)" if s.interpretation_method == "llm" else "Rule-based",
        })
    ctx["source_appendix"] = appendix

    last_run = db.scalars(select(CrawlRun).where(CrawlRun.company_id == company.id).order_by(CrawlRun.started_at.desc()).limit(1)).first()
    n_sources = db.scalar(select(func.count()).select_from(Source).where(Source.company_id == company.id, Source.approval_status == "approved")) or 0
    stats = {
        "lookback_days": lookback,
        "meaningful_signals": len(sigs),
        "by_category": {k: len(v) for k, v in by_cat.items()},
        "internal_signals": len(internal),
        "approved_sources": n_sources,
        "last_crawl": {"started": last_run.started_at.isoformat(), "status": last_run.status, "message": last_run.message} if last_run else None,
        "high_priority": sum(1 for s in sigs if s.priority == "high"),
        "opportunities": len(opps),
        "risks": len(risks),
    }
    narrative = _narrative(company, sigs, exec_items, opps, risks, stats, use_llm)
    ctx["narrative"] = narrative
    ctx["methodology"] = {
        "ranking": "Priority = 100 × (0.30·relevance + 0.25·impact + 0.15·urgency + 0.10·source credibility + 0.10·recency + 0.10·novelty). High ≥ 60, Medium ≥ 45.",
        "evidence_policy": "Every development links to its original source. Verification status, source reliability and evidence strength are reported separately; AI output is interpretation, never proof.",
        "window": f"Developments published (or, if undated, discovered) between {start.date()} and {end.date()}.",
    }
    content = {
        "company": {"id": company.id, "name": company.name, "website": company.website, "industry": company.industry or (company.profile or {}).get("industry")},
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "generated_at": end.isoformat(),
        **ctx,
    }
    title = f"Monday Morning Intelligence Brief — {company.name} — week of {end.date().isoformat()}"
    brief = Brief(company_id=company.id, title=title, period_start=start, period_end=end, trigger=trigger, content=content, stats=stats, job_run_id=job_run_id)
    brief.markdown = render_markdown(brief)
    db.add(brief)
    db.flush()
    for a in actions:
        db.add(BriefAction(brief_id=brief.id, company_id=company.id, signal_id=a["signal_id"], action=a["action"], reason=a["reason"], owner=a["owner"], priority=a["priority"]))
    db.flush()
    return brief


def _narrative(company: Company, sigs, exec_items, opps, risks, stats, use_llm: bool) -> dict:
    if not sigs:
        text = f"No meaningful external developments for {company.name} were detected in the last {stats['lookback_days']} days across {stats['approved_sources']} approved sources. This brief therefore contains no invented items."
        return {"text": text, "method": "rule-based"}
    cats = ", ".join(f"{n} {k}" for k, n in stats["by_category"].items())
    top = exec_items[0]
    text = (f"{len(sigs)} meaningful developments ({cats}) were identified from {stats['approved_sources']} approved sources. "
            f"The highest-priority item is “{nlp.truncate(top.title, 110)}” ({top.priority}, score {top.priority_score:.0f}). "
            f"{len(opps)} opportunities and {len(risks)} risks are supported by evidence this period.")
    method = "rule-based (deterministic summary of the ranked evidence)"
    llm = get_llm()
    if False and use_llm and llm.available:  # disabled: free-form LLM narrative proved prone to unsupported claims
        bullets = "\n".join(f"- [{s.category}/{s.polarity}] {s.title} ({s.publisher}, {s.event_date.date() if s.event_date else 'undated'}): {s.why_it_matters}" for s in exec_items)
        out = llm.generate(
            f"Write a 3-sentence executive summary for the founder of {company.name} using ONLY these evidence-backed items. "
            f"Do not add facts, numbers or names that are not present.\n{bullets}", max_tokens=160)
        if out and len(out) > 80:
            text = out.strip() + "\n\n(Counts: " + text.split(" were identified")[0] + ".)"
            method = "AI-assisted (local LLM) from the evidence-backed items below"
    return {"text": text, "method": method}


# ---------------------------------------------------------------- rendering
def _md_item(i: dict, show_action: bool = True) -> str:
    lines = [f"**{i['title']}** `[{i['ref']}]`"]
    meta = [i.get("publisher") or "source", f"published {i['when'] or 'date unknown'}", f"priority **{i['priority']}** ({i['priority_score']:.0f})", i["verification"]]
    if i.get("competitor"):
        meta.insert(0, f"competitor: {i['competitor']}")
    lines.append("  - " + " · ".join(meta))
    if i.get("evidence"):
        lines.append(f"  - *Evidence:* “{nlp.truncate(i['evidence'], 260)}” — [source]({i['evidence_url']})" if (i.get("evidence_url") or "").startswith("http") else f"  - *Evidence:* “{nlp.truncate(i['evidence'], 260)}” ({i.get('publisher')})")
    lines.append(f"  - *Why it matters ({i['interpretation'].lower()}):* {i['why_it_matters']}")
    lines.append(f"  - *Impact:* {i['polarity']} · {i['business_area']} · impact {i['impact']:.2f}, urgency {i['urgency']:.2f}, relevance {i['relevance']:.2f}")
    if show_action and i.get("recommended_action"):
        lines.append(f"  - *Recommended action:* {i['recommended_action']}")
    return "\n".join(lines)


def render_markdown(brief: Brief) -> str:
    c = brief.content
    out = [f"# {brief.title}", "", f"*Company:* {c['company']['name']} ({c['company']['website']}) · *Industry:* {c['company'].get('industry') or 'n/a'}",
           f"*Period:* {c['period']['start'][:10]} → {c['period']['end'][:10]} · *Generated:* {c['generated_at'][:16].replace('T', ' ')} UTC · *Trigger:* {brief.trigger}", "",
           f"> {c['narrative']['text']}", f"> *Summary method: {c['narrative']['method']}*", ""]
    out += ["## 1. Executive Summary", ""]
    if c["executive_summary"]:
        for n, i in enumerate(c["executive_summary"], 1):
            out.append(f"{n}. " + _md_item(i).replace("\n", "\n   "))
    else:
        out.append("No meaningful developments were detected in this period.")
    out += ["", "## 2. Customer Signals", ""]
    cs = c["customer_signals"]
    if cs["empty_message"]:
        out.append(cs["empty_message"])
    else:
        out.append("Themes: " + ", ".join(f"{t['type'].replace('_', ' ')} ({t['count']})" for t in cs["themes"]) + (f" · average sentiment {cs['average_sentiment']:+.2f}" if cs["average_sentiment"] is not None else ""))
        out.append("")
        out += ["- " + _md_item(i).replace("\n", "\n  ") for i in cs["items"]]
    out += ["", "## 3. Competitor Intelligence", ""]
    ci = c["competitor_intelligence"]
    if ci["empty_message"]:
        out.append(ci["empty_message"])
    for g in ci["groups"]:
        out += [f"### {g['competitor']}", ""] + ["- " + _md_item(i).replace("\n", "\n  ") for i in g["items"]] + [""]
    out += ["", "## 4. Market Intelligence", ""]
    mi = c["market_intelligence"]
    if mi["empty_message"]:
        out.append(mi["empty_message"])
    else:
        out += ["**Material to the business**", ""] + (["- " + _md_item(i).replace("\n", "\n  ") for i in mi["material"]] or ["- None this period."])
        out += ["", "**General industry context (lower materiality)**", ""] + (["- " + _md_item(i, False).replace("\n", "\n  ") for i in mi["general"]] or ["- None."])
    out += ["", "## 5. Internal Business Intelligence", ""]
    ii = c["internal_intelligence"]
    if ii["empty_message"]:
        out.append(ii["empty_message"])
    else:
        if ii.get("synthetic_note"):
            out.append(f"> ⚠️ **SYNTHETIC TEST DATA.** {ii['synthetic_note']}")
            out.append("")
        out.append("Documents analysed: " + "; ".join(f"{'[SYNTHETIC] ' if d.get('synthetic') else ''}{d['filename']} ({d['records']} records, uploaded {d['uploaded']})" + (f" — {d['description']}" if d.get("description") else "") for d in ii["documents"]))
        out.append("")
        out += ["- " + _md_item(i).replace("\n", "\n  ") for i in ii["items"]]
    out += ["", "## 6. Opportunities Identified", ""]
    for n, i in enumerate(c["opportunities"], 1):
        out.append(f"{n}. **{i['title']}** `[{i['ref']}]` — priority **{i['priority']}**\n   - *Evidence:* {nlp.truncate(i['evidence'] or '', 200)}\n   - *Impact:* {i['why_it_matters']}\n   - *Next step:* {i['next_step']}")
    if c.get("opportunities_note"):
        out.append(f"\n*{c['opportunities_note']}*")
    out += ["", "## 7. Risks & Threats", ""]
    for n, i in enumerate(c["risks"], 1):
        out.append(f"{n}. **{i['title']}** `[{i['ref']}]` — urgency {i['urgency']:.2f}, priority **{i['priority']}**\n   - *Possible impact:* {i['why_it_matters']}\n   - *Evidence:* {nlp.truncate(i['evidence'] or '', 200)}")
    if c.get("risks_note"):
        out.append(c["risks_note"])
    out += ["", "## 8. Recommended Actions for This Week", ""]
    if c["recommended_actions"]:
        out += ["| # | Action | Reason | Suggested owner | Priority |", "|---|---|---|---|---|"]
        for n, a in enumerate(c["recommended_actions"], 1):
            out.append(f"| {n} | {a['action']} | {a['reason']} | {a['owner']} | {a['priority']} |")
    else:
        out.append("No actions recommended — no evidence-backed developments required a response.")
    out += ["", "## 9. What We Should Watch", ""]
    out += [f"- **{w['title']}** — {w['why']}" + (f" `[{w['ref']}]`" if w.get("ref") else "") for w in c["watch_list"]] or ["- Nothing flagged for watching this period."]
    out += ["", "## 10. Source Appendix", "", "| Ref | Development | Source | Published | Discovered | Verification | Reliability | Evidence strength | Relevance |", "|---|---|---|---|---|---|---|---|---|"]
    for a in c["source_appendix"]:
        link = f"[{nlp.truncate(a['title'], 70).replace('|', '/')}]({a['url']})" if (a["url"] or "").startswith("http") else nlp.truncate(a["title"], 70).replace("|", "/")
        out.append(f"| {a['ref']} | {link} | {(a['source'] or '').replace('|', '/')} | {a['published']} | {a['discovered']} | {a['verification']} | {a['source_reliability']:.2f} | {a['evidence_strength']:.2f} | {a['strategic_relevance']:.2f} |")
    out += ["", "**Evidence snippets**", ""]
    out += [f"- `{a['ref']}` “{nlp.truncate(a['snippet'] or '', 300)}” — {a['url']}" for a in c["source_appendix"]]
    out += ["", "---", f"*Methodology:* {c['methodology']['ranking']} {c['methodology']['evidence_policy']} {c['methodology']['window']}"]
    return "\n".join(out)


def render_html(brief: Brief) -> str:
    import markdown

    body = markdown.markdown(brief.markdown, extensions=["tables", "sane_lists"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(brief.title)}</title>
<style>
@page {{ size: A4; margin: 1.6cm; }}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #111827; line-height: 1.45; }}
h1 {{ font-size: 18pt; color: #0f172a; border-bottom: 2px solid #4f46e5; padding-bottom: 6px; }}
h2 {{ font-size: 13pt; color: #312e81; margin-top: 18px; border-bottom: 1px solid #e5e7eb; padding-bottom: 3px; }}
h3 {{ font-size: 11pt; color: #1e293b; }}
blockquote {{ background: #eef2ff; border-left: 4px solid #4f46e5; margin: 8px 0; padding: 6px 10px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 8pt; }}
th, td {{ border: 1px solid #d1d5db; padding: 3px 4px; vertical-align: top; }}
th {{ background: #f3f4f6; }}
code {{ background: #f3f4f6; padding: 0 3px; font-size: 8pt; }}
a {{ color: #4338ca; }}
</style></head><body>{body}</body></html>"""


def render_pdf(brief: Brief) -> bytes:
    from xhtml2pdf import pisa
    import io

    buf = io.BytesIO()
    result = pisa.CreatePDF(render_html(brief), dest=buf, encoding="utf-8")
    if result.err:
        raise RuntimeError("PDF rendering failed")
    return buf.getvalue()
