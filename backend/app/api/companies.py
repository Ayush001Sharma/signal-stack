"""Companies, profile facts, interview, competitors, context changes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_company, owned
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Company, Competitor, ContextChange, FactStatus, InterviewQuestion, ProfileFact
from app.schemas import (
    AnswerIn, CompanyCreate, CompanyOut, CompanySummary, CompanyUpdate, CompetitorCreate, CompetitorOut, CompetitorUpdate,
    ContextChangeOut, ContextChangeRequest, FactCreate, FactOut, FactUpdate, JobStarted, QuestionOut,
)
from app.services import nlp
from app.services.interview import TOPIC_LABEL, answer_question, generate_questions, next_question, ordered_questions
from app.services.jobs import JobAlreadyRunning, ensure_schedule, start_job
from app.services.scheduler import remove_company, sync_company

router = APIRouter(tags=["companies"])


def _start(job_type: str, company_id: int, **kw) -> JobStarted:
    try:
        return JobStarted(job_run_id=start_job(job_type, company_id, trigger="manual", **kw))
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/companies", response_model=list[CompanySummary])
def list_companies(db: Session = Depends(get_db)):
    return list(db.scalars(select(Company).order_by(Company.created_at)))


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyCreate, db: Session = Depends(get_db)):
    website = str(body.website).rstrip("/")
    domain = nlp.domain_of(website)
    if db.scalar(select(Company).where(Company.domain == domain)):
        raise HTTPException(status_code=409, detail=f"A company with domain {domain} already exists")
    c = Company(name=body.name, website=website, domain=domain, industry=body.industry, business_context=body.business_context, profile={}, keywords=[], research_summary={})
    db.add(c)
    db.flush()
    cfg = ensure_schedule(db, c, get_settings().default_timezone)
    db.commit()
    sync_company(cfg)
    if body.run_setup:
        start_job("setup", c.id, trigger="manual")
    db.refresh(c)
    return c


@router.get("/companies/{company_id}", response_model=CompanyOut)
def read_company(company: Company = Depends(get_company)):
    return company


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(body: CompanyUpdate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "profile" in data:
        company.profile = {**(company.profile or {}), **data.pop("profile")}
    for k, v in data.items():
        setattr(company, k, v)
    company.profile_version += 1
    db.flush()
    return company


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    remove_company(company.id)
    db.delete(company)


@router.post("/companies/{company_id}/research", response_model=JobStarted)
def rerun_research(company: Company = Depends(get_company)):
    return _start("research", company.id)


@router.post("/companies/{company_id}/setup", response_model=JobStarted)
def rerun_setup(company: Company = Depends(get_company)):
    return _start("setup", company.id)


# ---------------------------------------------------------------- facts
@router.get("/companies/{company_id}/facts", response_model=list[FactOut])
def list_facts(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    return list(db.scalars(select(ProfileFact).where(ProfileFact.company_id == company.id).order_by(ProfileFact.field, ProfileFact.id)))


@router.post("/companies/{company_id}/facts", response_model=FactOut, status_code=201)
def add_fact(body: FactCreate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    f = ProfileFact(company_id=company.id, origin="user", **body.model_dump())
    db.add(f)
    db.flush()
    return f


@router.patch("/companies/{company_id}/facts/{fact_id}", response_model=FactOut)
def update_fact(fact_id: int, body: FactUpdate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    f = owned(db.get(ProfileFact, fact_id), company, "Fact")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(f, k, v)
    if "value" in data and f.origin != "user":
        f.origin = "user"
        f.evidence = (f.evidence or "") + " [edited by user]"
    db.flush()
    return f


@router.delete("/companies/{company_id}/facts/{fact_id}", status_code=204)
def delete_fact(fact_id: int, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    db.delete(owned(db.get(ProfileFact, fact_id), company, "Fact"))


# ---------------------------------------------------------------- interview
@router.get("/companies/{company_id}/interview", response_model=dict)
def interview_state(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    qs = ordered_questions(db, company.id)
    nxt = next_question(db, company.id)
    primary = [q for q in qs if not q.is_followup]
    return {
        "questions": [QuestionOut.model_validate(q).model_dump(mode="json") for q in qs],
        "next": QuestionOut.model_validate(nxt).model_dump(mode="json") if nxt else None,
        "progress": {"primary_total": len(primary), "answered": sum(1 for q in qs if q.status == "answered"), "skipped": sum(1 for q in qs if q.status == "skipped"), "pending": sum(1 for q in qs if q.status == "pending"), "followups": sum(1 for q in qs if q.is_followup)},
        "topic_labels": TOPIC_LABEL,
        "complete": nxt is None and bool(qs),
    }


@router.post("/companies/{company_id}/interview/generate", response_model=list[QuestionOut])
def generate_interview(use_llm: bool = True, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    if company.status in ("created", "researching") and not company.profile:
        raise HTTPException(status_code=409, detail="Company research has not finished yet")
    return generate_questions(db, company, use_llm=use_llm)


@router.post("/companies/{company_id}/interview/questions/{question_id}/answer", response_model=dict)
def answer(question_id: int, body: AnswerIn, use_llm: bool = True, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    q = owned(db.get(InterviewQuestion, question_id), company, "Question")
    if not body.skip and not body.answer:
        raise HTTPException(status_code=422, detail="Provide an answer or set skip=true")
    res = answer_question(db, company, q, body.answer, skip=body.skip, confidential=body.confidential, use_llm=use_llm, answered_by=body.answered_by)
    db.flush()
    nxt = next_question(db, company.id)
    return {"question": QuestionOut.model_validate(q).model_dump(mode="json"), **res, "next": QuestionOut.model_validate(nxt).model_dump(mode="json") if nxt else None}


# ---------------------------------------------------------------- competitors
@router.get("/companies/{company_id}/competitors", response_model=list[CompetitorOut])
def list_competitors(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    return list(db.scalars(select(Competitor).where(Competitor.company_id == company.id).order_by(Competitor.status.desc(), Competitor.confidence.desc())))


@router.post("/companies/{company_id}/competitors", response_model=CompetitorOut, status_code=201)
def add_competitor(body: CompetitorCreate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    key = nlp.name_key(body.name)
    if db.scalar(select(Competitor).where(Competitor.company_id == company.id, Competitor.name_key == key)):
        raise HTTPException(status_code=409, detail="Competitor already exists")
    c = Competitor(company_id=company.id, name=body.name, name_key=key, website=str(body.website).rstrip("/") if body.website else None, description=body.description, kind=body.kind,
                   reason="Added manually by user", discovery_method="user", status="confirmed", confidence=1.0, evidence=[])
    db.add(c)
    db.flush()
    return c


@router.patch("/companies/{company_id}/competitors/{competitor_id}", response_model=CompetitorOut)
def update_competitor(competitor_id: int, body: CompetitorUpdate, company: Company = Depends(get_company), db: Session = Depends(get_db)):
    c = owned(db.get(Competitor, competitor_id), company, "Competitor")
    data = body.model_dump(exclude_unset=True)
    if "website" in data and data["website"]:
        data["website"] = str(data["website"]).rstrip("/")
    for k, v in data.items():
        setattr(c, k, v)
    db.flush()
    return c


@router.post("/companies/{company_id}/competitors/discover", response_model=JobStarted)
def rediscover_competitors(full_refresh: bool = False, company: Company = Depends(get_company)):
    """Re-run competitor discovery. full_refresh also proposes competitor sources and refreshes pending interview questions."""
    return _start("competitor_refresh" if full_refresh else "competitors", company.id)


# ---------------------------------------------------------------- context change
@router.post("/companies/{company_id}/context", response_model=JobStarted)
def change_context(body: ContextChangeRequest, company: Company = Depends(get_company)):
    return _start("reassess_context", company.id, industry=body.industry, business_context=body.business_context)


@router.get("/companies/{company_id}/context-changes", response_model=list[ContextChangeOut])
def list_context_changes(company: Company = Depends(get_company), db: Session = Depends(get_db)):
    return list(db.scalars(select(ContextChange).where(ContextChange.company_id == company.id).order_by(ContextChange.created_at.desc())))


FactStatus  # re-export for type checkers
