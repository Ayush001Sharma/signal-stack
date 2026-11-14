"""Job execution with persistent run records (JobRun). Used by the scheduler and manual triggers."""
from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable

from sqlalchemy import select

from app.core.db import session_scope
from app.models import Company, JobRun, ScheduleConfig, utcnow

log = logging.getLogger(__name__)
_running: set[tuple[str, int | None]] = set()
_running_lock = threading.Lock()


class JobAlreadyRunning(RuntimeError):
    pass


def _execute(job_run_id: int, job_type: str, company_id: int | None, fn: Callable, kwargs: dict) -> None:
    key = (job_type, company_id)
    try:
        with session_scope() as db:
            run = db.get(JobRun, job_run_id)
            run.status = "running"
            run.started_at = utcnow()
        with session_scope() as db:
            run = db.get(JobRun, job_run_id)
            company = db.get(Company, company_id) if company_id else None
            result = fn(db, company, run, **kwargs) or {}
            run.status = result.pop("_status", "success")
            run.message = result.pop("_message", None) or run.message
            run.details = {**(run.details or {}), **result}
            run.finished_at = utcnow()
        log.info("job finished", extra={"job": job_type, "company_id": company_id})
    except Exception as exc:
        log.exception("job failed", extra={"job": job_type, "company_id": company_id})
        with session_scope() as db:
            run = db.get(JobRun, job_run_id)
            if run:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-3000:]}"
                run.message = f"Failed: {type(exc).__name__}: {str(exc)[:300]}"
                run.finished_at = utcnow()
    finally:
        with _running_lock:
            _running.discard(key)


def start_job(job_type: str, company_id: int | None, trigger: str = "manual", background: bool = True, **kwargs) -> int:
    fn = JOB_FUNCS[job_type]
    key = (job_type, company_id)
    with _running_lock:
        if key in _running:
            raise JobAlreadyRunning(f"{job_type} is already running for company {company_id}")
        _running.add(key)
    try:
        with session_scope() as db:
            run = JobRun(company_id=company_id, job_type=job_type, trigger=trigger, status="queued", details={"kwargs": {k: v for k, v in kwargs.items() if isinstance(v, (int, str, bool, float, type(None)))}})
            db.add(run)
            db.flush()
            run_id = run.id
    except Exception:
        with _running_lock:
            _running.discard(key)
        raise
    if background:
        threading.Thread(target=_execute, args=(run_id, job_type, company_id, fn, kwargs), daemon=True, name=f"{job_type}-{company_id}").start()
    else:
        _execute(run_id, job_type, company_id, fn, kwargs)
    return run_id


# ---------------------------------------------------------------- job bodies
def job_research(db, company, run, use_llm: bool = True):
    from app.services.research import research_company

    s = research_company(db, company, use_llm=use_llm)
    return {"_message": f"Crawled {len(s['pages_crawled'])} pages, {s.get('developments_found', 0)} public developments.", "pages": s["pages_crawled"]}


def job_competitors(db, company, run):
    from app.services.competitors import discover_competitors

    comps = discover_competitors(db, company)
    return {"_message": f"Discovered {len(comps)} competitors/substitutes.", "competitors": [c.name for c in comps]}


def job_discovery(db, company, run):
    from app.services.discovery import discover_sources

    res = discover_sources(db, company)
    return {"_message": f"Proposed {res['created']} sources ({res['recommended']} recommended).", **{k: v for k, v in res.items() if k != "skipped"}}


def job_setup(db, company, run, use_llm: bool = True):
    """Research → competitor discovery → interview generation → source discovery."""
    from app.services.competitors import discover_competitors
    from app.services.discovery import discover_sources
    from app.services.interview import generate_questions
    from app.services.research import research_company

    steps = {}
    s = research_company(db, company, use_llm=use_llm)
    steps["research"] = f"{len(s['pages_crawled'])} pages"
    db.commit()
    comps = discover_competitors(db, company)
    steps["competitors"] = [c.name for c in comps]
    db.commit()
    qs = generate_questions(db, company, use_llm=use_llm)
    steps["questions"] = len(qs)
    db.commit()
    res = discover_sources(db, company)
    steps["sources"] = {k: v for k, v in res.items() if k != "skipped"}
    return {"_message": f"Setup complete: {len(comps)} competitors, {len(qs)} questions, {res['created']} sources proposed.", "steps": steps}


def job_crawl(db, company, run, source_ids: list[int] | None = None):
    from app.services.crawler import crawl_company

    cr = crawl_company(db, company, trigger=run.trigger, job_run_id=run.id, source_ids=source_ids)
    return {"_status": "success" if cr.status in ("success", "partial") else "failed", "_message": cr.message, "crawl_run_id": cr.id, "crawl_status": cr.status}


def job_weekly_brief(db, company, run, lookback_days: int | None = None, crawl: bool = True, use_llm: bool = True):
    from app.services.analysis import enrich_with_llm
    from app.services.briefs import generate_brief
    from app.services.crawler import crawl_company

    details = {}
    status = "success"
    if crawl:
        cr = crawl_company(db, company, trigger=run.trigger, job_run_id=run.id)
        details["crawl"] = {"id": cr.id, "status": cr.status, "message": cr.message}
        if cr.status == "failed":
            status = "partial"
        db.commit()
    if use_llm:
        details["llm_enriched"] = enrich_with_llm(db, company)
    brief = generate_brief(db, company, trigger=run.trigger, lookback_days=lookback_days, job_run_id=run.id, use_llm=use_llm)
    details["brief_id"] = brief.id
    return {"_status": status, "_message": f"Brief #{brief.id} generated with {brief.stats.get('meaningful_signals', 0)} meaningful signals.", **details}


def job_monthly_audit(db, company, run, discover: bool = True):
    from app.services.audit import run_audit

    rep = run_audit(db, company, trigger=run.trigger, job_run_id=run.id, discover=discover)
    s = rep.content["summary"]
    return {"_message": f"Audit #{rep.id}: {s['dead_or_unavailable']} unavailable, {s['duplicates']} duplicates, {s['inactive']} inactive, {s['recommended_additions']} additions recommended.", "audit_id": rep.id}


def job_reassess(db, company, run, industry: str | None = None, business_context: str | None = None):
    from app.services.audit import reassess_context

    cc = reassess_context(db, company, industry, business_context)
    return {"_message": cc.summary, "context_change_id": cc.id}


def job_competitor_refresh(db, company, run, use_llm: bool = True):
    """Competitor discovery → competitor source discovery → regenerate still-pending interview questions."""
    from app.services.competitors import discover_competitors
    from app.services.discovery import discover_sources
    from app.services.interview import generate_questions

    comps = discover_competitors(db, company, use_llm=use_llm)
    db.commit()
    res = discover_sources(db, company, categories=("competitors",))
    db.commit()
    qs = generate_questions(db, company, use_llm=use_llm)
    return {"_message": f"{len(comps)} competitors; {res['created']} competitor sources proposed; {len(qs)} questions refreshed.", "competitors": [c.name for c in comps]}


def job_reanalyze(db, company, run):
    from app.services.analysis import reanalyze_company

    r = reanalyze_company(db, company)
    return {"_message": f"Re-scored {r['external_signals']} external records ({r['meaningful']} meaningful) and {r['internal_signals']} internal themes.", **r}


JOB_FUNCS: dict[str, Callable] = {
    "reanalyze": job_reanalyze,
    "competitor_refresh": job_competitor_refresh,
    "research": job_research,
    "competitors": job_competitors,
    "discovery": job_discovery,
    "setup": job_setup,
    "crawl": job_crawl,
    "weekly_brief": job_weekly_brief,
    "monthly_audit": job_monthly_audit,
    "reassess_context": job_reassess,
}


def ensure_schedule(db, company: Company, default_tz: str) -> ScheduleConfig:
    cfg = db.scalar(select(ScheduleConfig).where(ScheduleConfig.company_id == company.id))
    if cfg is None:
        cfg = ScheduleConfig(company_id=company.id, timezone=default_tz)
        db.add(cfg)
        db.flush()
    return cfg
