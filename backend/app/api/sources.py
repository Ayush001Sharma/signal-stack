"""Source Manager: discovery, approval, manual add/remove, pause/resume, crawl history, items, crawling."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_company, owned
from app.core.db import get_db
from app.models import Company, Competitor, CrawlLog, CrawlRun, RawItem, Source
from app.schemas import BulkSourceAction, CrawlLogOut, CrawlRunOut, JobStarted, Page, RawItemOut, SourceCreate, SourceOut, SourceUpdate
from app.services import nlp
from app.services.discovery import Prober, credibility_for, mark_duplicates
from app.services.fetcher import get_fetcher
from app.services.jobs import JobAlreadyRunning, start_job

router = APIRouter(tags=["sources"])


@router.get("/companies/{company_id}/sources", response_model=list[SourceOut])
def list_sources(category: str | None = None, approval_status: str | None = None, health_status: str | None = None, q: str | None = None, include_removed: bool = False,
                 company: Company = Depends(get_company), db: Session = Depends(get_db)):
    stmt = select(Source).where(Source.company_id == company.id)
    if not include_removed:
        stmt = stmt.where(Source.approval_status != "removed")
    if category:
        stmt = stmt.where(Source.category == category)
    if approval_status:
        stmt = stmt.where(Source.approval_status == approval_status)
    if health_status:
        stmt = stmt.where(Source.health_status == health_status)
    if q:
        stmt = stmt.where(Source.name.ilike(f"%{q}%") | Source.url.ilike(f"%{q}%"))
    return list(db.scalars(stmt.order_by(Source.category, Source.approval_status, Source.expected_relevance.desc())))


@router.get("/companies/{company_id}/signal-stack", response_model=dict)
def signal_stack(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    srcs = list(db.scalars(select(Source).where(Source.company_id == company.id, Source.approval_status.in_(["approved", "pending"])).order_by(Source.expected_relevance.desc())))
    from app.models import InternalDocument

    docs = list(db.scalars(select(InternalDocument).where(InternalDocument.company_id == company.id)))
    comps = {c.id: c.name for c in db.scalars(select(Competitor).where(Competitor.company_id == company.id))}
    out = {}
    for cat in ("customers", "competitors", "market"):
        items = [SourceOut.model_validate(s).model_dump(mode="json") | {"competitor_name": comps.get(s.competitor_id)} for s in srcs if s.category == cat]
        out[cat] = {"sources": items, "approved": sum(1 for s in items if s["approval_status"] == "approved"), "pending": sum(1 for s in items if s["approval_status"] == "pending")}
    out["internal"] = {"documents": [{"id": d.id, "filename": d.filename, "status": d.status, "records": d.record_count, "uploaded_at": d.uploaded_at.isoformat()} for d in docs],
                       "approved": len(docs), "pending": 0, "sources": []}
    return out


@router.post("/companies/{company_id}/sources", response_model=SourceOut, status_code=201)
def add_source(body: SourceCreate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    url = str(body.url)
    norm = nlp.normalize_url(url)
    dup = db.scalar(select(Source).where(Source.company_id == company.id, Source.normalized_url == norm, Source.approval_status != "removed"))
    if dup:
        raise HTTPException(status_code=409, detail={"message": "Duplicate source", "duplicate_of_id": dup.id, "name": dup.name})
    comp = None
    if body.competitor_id:
        comp = owned(db.get(Competitor, body.competitor_id), company, "Competitor")
    fetcher = get_fetcher()
    if not fetcher.robots_allowed(url):
        raise HTTPException(status_code=422, detail="robots.txt of this site disallows automated access; the source cannot be monitored.")
    kind = body.source_type
    probe = Prober(company, fetcher).probe(url, kind if kind in ("stackexchange", "hackernews", "web_page", "news_search") else "rss")
    cred, label, why = credibility_for(url, kind, company, comp)
    src = Source(company_id=company.id, competitor_id=comp.id if comp else None, name=body.name, url=url, normalized_url=norm, category=body.category, source_type=kind,
                 description=body.description, reason=body.reason, credibility=cred, credibility_label=label, credibility_rationale=why,
                 expected_relevance=probe["relevance"] if probe else 0.0, relevance_rationale=(probe["why"] if probe else "Probe failed: source unreachable or returned no parsable items."),
                 update_frequency=probe["frequency"] if probe else "unknown", approval_status="approved" if body.approve else "pending", recommended=bool(probe and probe["count"]),
                 discovered_by="user", sample_items=probe.get("sample", []) if probe else [], config=body.config, health_status="healthy" if probe else "degraded",
                 last_error=None if probe else "Initial probe failed", last_new_item_at=probe.get("latest") if probe else None)
    db.add(src)
    db.flush()
    mark_duplicates(db, company.id)
    return src


@router.patch("/companies/{company_id}/sources/{source_id}", response_model=SourceOut)
def update_source(source_id: int, body: SourceUpdate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    s = owned(db.get(Source, source_id), company, "Source")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.flush()
    return s


@router.delete("/companies/{company_id}/sources/{source_id}", status_code=204)
def remove_source(source_id: int, hard: bool = False, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    """Remove a source. Default is a soft remove that keeps crawl history and evidence for audit."""
    s = owned(db.get(Source, source_id), company, "Source")
    if hard:
        db.delete(s)
    else:
        s.approval_status = "removed"
        s.monitoring_status = "paused"


@router.post("/companies/{company_id}/sources/bulk", response_model=dict)
def bulk(body: BulkSourceAction, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    if body.action == "approve_recommended":
        srcs = list(db.scalars(select(Source).where(Source.company_id == company.id, Source.approval_status == "pending", Source.recommended.is_(True), Source.duplicate_of_id.is_(None))))
    else:
        srcs = list(db.scalars(select(Source).where(Source.company_id == company.id, Source.id.in_(body.source_ids))))
    for s in srcs:
        if body.action in ("approve", "approve_recommended"):
            s.approval_status = "approved"
        elif body.action == "reject":
            s.approval_status = "rejected"
        elif body.action == "pause":
            s.monitoring_status = "paused"
        elif body.action == "resume":
            s.monitoring_status = "active"
        elif body.action == "remove":
            s.approval_status, s.monitoring_status = "removed", "paused"
    db.flush()
    return {"updated": len(srcs), "action": body.action}


@router.get("/companies/{company_id}/sources/duplicates", response_model=list[dict])
def duplicates(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    mark_duplicates(db, company.id)
    out = []
    for s in db.scalars(select(Source).where(Source.company_id == company.id, Source.duplicate_of_id.is_not(None), Source.approval_status != "removed")):
        orig = db.get(Source, s.duplicate_of_id)
        out.append({"source_id": s.id, "name": s.name, "url": s.url, "duplicate_of_id": orig.id, "duplicate_of_name": orig.name})
    return out


@router.get("/companies/{company_id}/sources/{source_id}/history", response_model=list[CrawlLogOut])
def source_history(source_id: int, limit: int = Query(50, le=500), company: Company = Depends(get_company), db: Session = Depends(get_db)):
    owned(db.get(Source, source_id), company, "Source")
    return list(db.scalars(select(CrawlLog).where(CrawlLog.source_id == source_id).order_by(CrawlLog.started_at.desc()).limit(limit)))


@router.get("/companies/{company_id}/sources/{source_id}/items", response_model=list[RawItemOut])
def source_items(source_id: int, limit: int = Query(50, le=500), company: Company = Depends(get_company), db: Session = Depends(get_db)):
    owned(db.get(Source, source_id), company, "Source")
    return list(db.scalars(select(RawItem).where(RawItem.source_id == source_id).order_by(RawItem.discovered_at.desc()).limit(limit)))


@router.post("/companies/{company_id}/sources/{source_id}/check", response_model=JobStarted)
def check_source(source_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    owned(db.get(Source, source_id), company, "Source")
    try:
        return JobStarted(job_run_id=start_job("crawl", company.id, trigger="manual", source_ids=[source_id]))
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/companies/{company_id}/sources/discover", response_model=JobStarted)
def rediscover(company: Company = Depends(get_company)):
    try:
        return JobStarted(job_run_id=start_job("discovery", company.id, trigger="manual"))
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/companies/{company_id}/crawl", response_model=JobStarted)
def crawl_now(company: Company = Depends(get_company)):
    try:
        return JobStarted(job_run_id=start_job("crawl", company.id, trigger="manual"))
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/companies/{company_id}/crawl-runs", response_model=Page[CrawlRunOut])
def crawl_runs(p: Pagination = Depends(), company: Company = Depends(get_company), db: Session = Depends(get_db)):
    base = select(CrawlRun).where(CrawlRun.company_id == company.id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    items = list(db.scalars(base.order_by(CrawlRun.started_at.desc()).offset(p.offset).limit(p.page_size)))
    return Page(items=items, total=total, page=p.page, page_size=p.page_size)


@router.get("/companies/{company_id}/crawl-logs", response_model=Page[CrawlLogOut])
def crawl_logs(status: str | None = None, p: Pagination = Depends(), company: Company = Depends(get_company), db: Session = Depends(get_db)):
    base = select(CrawlLog).where(CrawlLog.company_id == company.id)
    if status:
        base = base.where(CrawlLog.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    items = list(db.scalars(base.order_by(CrawlLog.started_at.desc()).offset(p.offset).limit(p.page_size)))
    return Page(items=items, total=total, page=p.page, page_size=p.page_size)
