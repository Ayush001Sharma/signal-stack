"""Dashboard overview, jobs/scheduler, uploads, settings and system status."""
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_company, owned
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Brief, Company, CrawlRun, InternalDocument, JobRun, RawItem, ScheduleConfig, Signal, Source, utcnow
from app.schemas import BriefSummary, CompanySummary, DashboardOut, DocumentOut, JobRunOut, Page, ScheduleOut, ScheduleUpdate, SignalOut
from app.services import nlp
from app.services.internal import UploadError, save_upload
from app.services.jobs import ensure_schedule
from app.services.llm import get_llm
from app.services.scheduler import get_scheduler, list_jobs, sync_company

router = APIRouter(tags=["operations"])


@router.get("/companies/{company_id}/dashboard", response_model=DashboardOut)
def dashboard(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    cid = company.id
    week = utcnow() - timedelta(days=7)
    approved = db.scalar(select(func.count()).select_from(Source).where(Source.company_id == cid, Source.approval_status == "approved")) or 0
    health = {k: v for k, v in db.execute(select(Source.health_status, func.count()).where(Source.company_id == cid, Source.approval_status == "approved").group_by(Source.health_status))}
    by_cat = {k: v for k, v in db.execute(select(Source.category, func.count()).where(Source.company_id == cid, Source.approval_status == "approved").group_by(Source.category))}
    pending = db.scalar(select(func.count()).select_from(Source).where(Source.company_id == cid, Source.approval_status == "pending")) or 0
    m = select(Signal).where(Signal.company_id == cid, Signal.is_meaningful.is_(True), Signal.status != "dismissed")
    cnt = lambda stmt: db.scalar(select(func.count()).select_from(stmt.subquery())) or 0  # noqa: E731
    signals = {
        "total_meaningful": cnt(m),
        "new_this_week": cnt(m.where(Signal.discovered_at >= week)),
        "high_priority": cnt(m.where(Signal.priority == "high")),
        "opportunities": cnt(m.where(Signal.polarity == "opportunity")),
        "risks": cnt(m.where(Signal.polarity == "threat")),
        "by_category": {k: v for k, v in db.execute(select(Signal.category, func.count()).where(Signal.company_id == cid, Signal.is_meaningful.is_(True)).group_by(Signal.category))},
        "raw_items": db.scalar(select(func.count()).select_from(RawItem).where(RawItem.company_id == cid)) or 0,
    }
    latest = db.scalars(select(Brief).where(Brief.company_id == cid).order_by(Brief.generated_at.desc()).limit(1)).first()
    runs = list(db.scalars(select(CrawlRun).where(CrawlRun.company_id == cid).order_by(CrawlRun.started_at.desc()).limit(5)))
    jobs = list(db.scalars(select(JobRun).where(JobRun.company_id == cid).order_by(JobRun.started_at.desc()).limit(6)))
    activity = [{"kind": "crawl", "at": r.started_at.isoformat(), "status": r.status, "message": r.message} for r in runs] + [{"kind": j.job_type, "at": j.started_at.isoformat(), "status": j.status, "message": j.message} for j in jobs]
    activity.sort(key=lambda a: a["at"], reverse=True)
    date_col = func.date_trunc("day", func.coalesce(Signal.event_date, Signal.discovered_at))
    trend_rows = db.execute(select(date_col, Signal.category, func.count()).where(Signal.company_id == cid, Signal.is_meaningful.is_(True), func.coalesce(Signal.event_date, Signal.discovered_at) >= utcnow() - timedelta(days=30)).group_by(date_col, Signal.category).order_by(date_col))
    trend: dict[str, dict] = {}
    for d, cat, n in trend_rows:
        key = d.date().isoformat()
        trend.setdefault(key, {"date": key, "customers": 0, "competitors": 0, "market": 0, "internal": 0})[cat] = n
    top = list(db.scalars(m.order_by(Signal.priority_score.desc()).limit(5)))
    failed = list(db.scalars(select(JobRun).where(JobRun.company_id == cid, JobRun.status == "failed").order_by(JobRun.started_at.desc()).limit(5)))
    from app.api.signals import _decorate

    return DashboardOut(
        company=CompanySummary.model_validate(company),
        sources={"approved": approved, "pending": pending, "health": health, "by_category": by_cat},
        signals=signals,
        latest_brief=BriefSummary.model_validate(latest) if latest else None,
        recent_activity=activity[:10],
        upcoming_jobs=list_jobs(cid),
        signal_trend=list(trend.values()),
        top_signals=_decorate(db, top),
        failed_jobs=[JobRunOut.model_validate(j) for j in failed],
    )


# ---------------------------------------------------------------- jobs & schedule
@router.get("/jobs", response_model=Page[JobRunOut])
def job_runs(company_id: int | None = None, status: str | None = None, job_type: str | None = None, p: Pagination = Depends(), db: Session = Depends(get_db)):
    base = select(JobRun)
    if company_id:
        base = base.where(JobRun.company_id == company_id)
    if status:
        base = base.where(JobRun.status == status)
    if job_type:
        base = base.where(JobRun.job_type == job_type)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    return Page(items=list(db.scalars(base.order_by(JobRun.started_at.desc()).offset(p.offset).limit(p.page_size))), total=total, page=p.page, page_size=p.page_size)


@router.get("/jobs/{job_id}", response_model=JobRunOut)
def job_run(job_id: int, db: Session = Depends(get_db)):
    j = db.get(JobRun, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j


@router.get("/scheduler", response_model=dict)
def scheduler_status():
    sch = get_scheduler()
    return {"running": bool(sch and sch.running), "jobs": list_jobs()}


@router.get("/companies/{company_id}/schedule", response_model=ScheduleOut)
def get_schedule(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    return ensure_schedule(db, company, get_settings().default_timezone)


@router.put("/companies/{company_id}/schedule", response_model=ScheduleOut)
def put_schedule(body: ScheduleUpdate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    cfg = ensure_schedule(db, company, get_settings().default_timezone)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cfg, k, v)
    db.flush()
    db.commit()
    sync_company(cfg)
    return cfg


# ---------------------------------------------------------------- uploads
@router.post("/companies/{company_id}/documents", response_model=DocumentOut, status_code=201)
async def upload(file: UploadFile = File(...), description: str | None = Form(None), company: Company = Depends(get_company), db: Session = Depends(get_db)):
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    try:
        doc = save_upload(db, company, file.filename or "", file.content_type, data, description)
    except UploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return doc


@router.get("/companies/{company_id}/documents", response_model=list[DocumentOut])
def documents(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    return list(db.scalars(select(InternalDocument).where(InternalDocument.company_id == company.id).order_by(InternalDocument.uploaded_at.desc())))


@router.delete("/companies/{company_id}/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    import os

    d = owned(db.get(InternalDocument, doc_id), company, "Document")
    try:
        os.remove(d.stored_path)
    except OSError:
        pass
    db.delete(d)


# ---------------------------------------------------------------- settings / system
@router.get("/system", response_model=dict)
def system(db: Session = Depends(get_db)):
    s = get_settings()
    return {
        "app": s.app_name,
        "environment": s.environment,
        "llm": get_llm().status(),
        "embeddings": nlp.get_embedder().backend,
        "scheduler": {"enabled": s.scheduler_enabled, "running": bool(get_scheduler() and get_scheduler().running)},
        "auth": "api_key" if s.api_key else "local-demo (no API key configured)",
        "crawler": {"user_agent": s.crawler_user_agent, "per_host_delay_seconds": s.per_host_delay_seconds, "timeout_seconds": s.request_timeout_seconds, "max_retries": s.max_retries, "respects_robots_txt": True},
        "reddit_api_configured": bool(s.reddit_client_id and s.reddit_client_secret),
        "upload_limit_mb": s.max_upload_mb,
        "counts": {"companies": db.scalar(select(func.count()).select_from(Company)), "sources": db.scalar(select(func.count()).select_from(Source)), "raw_items": db.scalar(select(func.count()).select_from(RawItem)),
                   "signals": db.scalar(select(func.count()).select_from(Signal)), "briefs": db.scalar(select(func.count()).select_from(Brief))},
    }
