"""Monday Briefs (generate, history, exports, action tracking) and monthly audits."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_company, owned
from app.core.db import get_db
from app.models import AuditReport, Brief, BriefAction, Company
from app.schemas import AuditOut, BriefActionOut, BriefActionUpdate, BriefOut, BriefRequest, BriefSummary, JobStarted, Page
from app.services.briefs import render_html, render_pdf
from app.services.jobs import JobAlreadyRunning, start_job

router = APIRouter(tags=["briefs"])


def _start(job_type, company_id, **kw):
    try:
        return JobStarted(job_run_id=start_job(job_type, company_id, trigger="manual", **kw))
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/companies/{company_id}/briefs", response_model=JobStarted)
def generate(body: BriefRequest, company: Company = Depends(get_company)):
    """Run the weekly brief pipeline now (crawl → analyse → rank → generate → save)."""
    return _start("weekly_brief", company.id, lookback_days=body.lookback_days, crawl=body.crawl, use_llm=body.use_llm)


@router.get("/companies/{company_id}/briefs", response_model=Page[BriefSummary])
def history(p: Pagination = Depends(), company: Company = Depends(get_company), db: Session = Depends(get_db)):
    base = select(Brief).where(Brief.company_id == company.id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    return Page(items=list(db.scalars(base.order_by(Brief.generated_at.desc()).offset(p.offset).limit(p.page_size))), total=total, page=p.page, page_size=p.page_size)


@router.get("/companies/{company_id}/briefs/latest", response_model=BriefOut)
def latest(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    b = db.scalars(select(Brief).where(Brief.company_id == company.id).order_by(Brief.generated_at.desc()).limit(1)).first()
    if not b:
        raise HTTPException(status_code=404, detail="No brief generated yet")
    return b


@router.get("/companies/{company_id}/briefs/{brief_id}", response_model=BriefOut)
def get_brief(brief_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    return owned(db.get(Brief, brief_id), company, "Brief")


@router.get("/companies/{company_id}/briefs/{brief_id}/markdown", response_class=PlainTextResponse)
def export_md(brief_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    b = owned(db.get(Brief, brief_id), company, "Brief")
    return PlainTextResponse(b.markdown, media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="brief-{company.domain}-{b.generated_at.date()}.md"'})


@router.get("/companies/{company_id}/briefs/{brief_id}/html", response_class=HTMLResponse)
def export_html(brief_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    """Print-friendly / email-ready HTML."""
    return HTMLResponse(render_html(owned(db.get(Brief, brief_id), company, "Brief")))


@router.get("/companies/{company_id}/briefs/{brief_id}/pdf")
def export_pdf(brief_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    b = owned(db.get(Brief, brief_id), company, "Brief")
    return Response(render_pdf(b), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="brief-{company.domain}-{b.generated_at.date()}.pdf"'})


@router.get("/companies/{company_id}/briefs/{brief_id}/actions", response_model=list[BriefActionOut])
def actions(brief_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    owned(db.get(Brief, brief_id), company, "Brief")
    return list(db.scalars(select(BriefAction).where(BriefAction.brief_id == brief_id).order_by(BriefAction.id)))


@router.patch("/companies/{company_id}/actions/{action_id}", response_model=BriefActionOut)
def update_action(action_id: int, body: BriefActionUpdate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    a = owned(db.get(BriefAction, action_id), company, "Action")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.flush()
    return a


@router.post("/companies/{company_id}/audits", response_model=JobStarted)
def run_audit(discover: bool = True, company: Company = Depends(get_company)):
    return _start("monthly_audit", company.id, discover=discover)


@router.get("/companies/{company_id}/audits", response_model=list[AuditOut])
def audits(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    return list(db.scalars(select(AuditReport).where(AuditReport.company_id == company.id).order_by(AuditReport.generated_at.desc()).limit(24)))


@router.get("/companies/{company_id}/audits/{audit_id}", response_model=AuditOut)
def audit(audit_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    return owned(db.get(AuditReport, audit_id), company, "Audit")
