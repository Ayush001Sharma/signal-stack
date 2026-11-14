"""Intelligence Feed: filterable, searchable, paginated signals with full score breakdown."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_company, owned
from app.core.db import get_db
from app.models import Company, Competitor, RawItem, Signal, Source
from app.schemas import Page, SignalOut, SignalUpdate

router = APIRouter(tags=["signals"])


def _decorate(db: Session, sigs: list[Signal]) -> list[SignalOut]:
    src_ids = {s.source_id for s in sigs if s.source_id}
    comp_ids = {s.competitor_id for s in sigs if s.competitor_id}
    srcs = {s.id: s.name for s in db.scalars(select(Source).where(Source.id.in_(src_ids)))} if src_ids else {}
    comps = {c.id: c.name for c in db.scalars(select(Competitor).where(Competitor.id.in_(comp_ids)))} if comp_ids else {}
    out = []
    for s in sigs:
        o = SignalOut.model_validate(s)
        o.source_name = srcs.get(s.source_id)
        o.competitor_name = comps.get(s.competitor_id)
        out.append(o)
    return out


@router.get("/companies/{company_id}/signals", response_model=Page[SignalOut])
def list_signals(
    category: str | None = None,
    competitor_id: int | None = None,
    priority: str | None = None,
    polarity: str | None = None,
    verification_status: str | None = None,
    signal_type: str | None = None,
    min_relevance: float | None = Query(None, ge=0, le=1),
    min_impact: float | None = Query(None, ge=0, le=1),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = Query(None, max_length=200),
    meaningful_only: bool = True,
    include_dismissed: bool = False,
    sort: str = Query("priority", pattern="^(priority|date|discovered|relevance|impact)$"),
    p: Pagination = Depends(),
    company: Company = Depends(get_company),
    db: Session = Depends(get_db),
):
    stmt = select(Signal).where(Signal.company_id == company.id)
    if meaningful_only:
        stmt = stmt.where(Signal.is_meaningful.is_(True))
    if not include_dismissed:
        stmt = stmt.where(Signal.status != "dismissed")
    for col, val in ((Signal.category, category), (Signal.competitor_id, competitor_id), (Signal.priority, priority), (Signal.polarity, polarity), (Signal.verification_status, verification_status), (Signal.signal_type, signal_type)):
        if val is not None:
            stmt = stmt.where(col == val)
    if min_relevance is not None:
        stmt = stmt.where(Signal.relevance >= min_relevance)
    if min_impact is not None:
        stmt = stmt.where(Signal.impact >= min_impact)
    date_col = func.coalesce(Signal.event_date, Signal.discovered_at)
    if date_from:
        stmt = stmt.where(date_col >= date_from)
    if date_to:
        stmt = stmt.where(date_col <= date_to)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Signal.title.ilike(like), Signal.what_happened.ilike(like), Signal.publisher.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"priority": Signal.priority_score.desc(), "date": date_col.desc(), "discovered": Signal.discovered_at.desc(), "relevance": Signal.relevance.desc(), "impact": Signal.impact.desc()}[sort]
    sigs = list(db.scalars(stmt.order_by(order, Signal.id.desc()).offset(p.offset).limit(p.page_size)))
    return Page(items=_decorate(db, sigs), total=total, page=p.page, page_size=p.page_size)


@router.get("/companies/{company_id}/signals/{signal_id}", response_model=dict)
def get_signal(signal_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    s = owned(db.get(Signal, signal_id), company, "Signal")
    raw = db.get(RawItem, s.raw_item_id) if s.raw_item_id else None
    return {"signal": _decorate(db, [s])[0].model_dump(mode="json"),
            "raw_evidence": {"id": raw.id, "url": raw.url, "title": raw.title, "snippet": raw.snippet, "content": (raw.content or "")[:5000], "publisher": raw.publisher, "published_at": raw.published_at, "discovered_at": raw.discovered_at, "version": raw.version, "item_type": raw.item_type, "date_source": raw.date_source, "extra": raw.extra} if raw else None}


@router.patch("/companies/{company_id}/signals/{signal_id}", response_model=SignalOut)
def update_signal(signal_id: int, body: SignalUpdate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    s = owned(db.get(Signal, signal_id), company, "Signal")
    s.status = body.status
    db.flush()
    return _decorate(db, [s])[0]


@router.get("/companies/{company_id}/signals-facets", response_model=dict)
def facets(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    def group(col):
        return {k: v for k, v in db.execute(select(col, func.count()).where(Signal.company_id == company.id, Signal.is_meaningful.is_(True)).group_by(col))}
    comps = [{"id": c.id, "name": c.name} for c in db.scalars(select(Competitor).where(Competitor.company_id == company.id, Competitor.status != "rejected"))]
    return {"category": group(Signal.category), "priority": group(Signal.priority), "polarity": group(Signal.polarity), "verification_status": group(Signal.verification_status), "signal_type": group(Signal.signal_type), "competitors": comps,
            "total_collected": db.scalar(select(func.count()).select_from(Signal).where(Signal.company_id == company.id)), "raw_items": db.scalar(select(func.count()).select_from(RawItem).where(RawItem.company_id == company.id))}


@router.post("/companies/{company_id}/signals/reanalyze", response_model=dict)
def reanalyze(company: Company = Depends(get_company)):
    """Rebuild all signals from stored evidence with the current ranking rules and company profile."""
    from fastapi import HTTPException

    from app.services.jobs import JobAlreadyRunning, start_job

    try:
        return {"job_run_id": start_job("reanalyze", company.id, trigger="manual"), "status": "queued"}
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
