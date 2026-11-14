"""Print acceptance metrics straight from the database (used for docs/PROJECT_AUDIT.md)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from sqlalchemy import func, select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models import AuditReport, Brief, Company, Competitor, ContextChange, CrawlLog, CrawlRun, InterviewQuestion, InternalDocument, JobRun, RawItem, Signal, Source  # noqa: E402

db = SessionLocal()
tot_records = 0
for c in db.scalars(select(Company).order_by(Company.id)):
    cnt = lambda m, *w: db.scalar(select(func.count()).select_from(m).where(m.company_id == c.id, *w)) or 0  # noqa: E731
    by_cat = dict(db.execute(select(Source.category, func.count()).where(Source.company_id == c.id, Source.approval_status == "approved").group_by(Source.category)).all())
    meaningful_ext = cnt(Signal, Signal.is_meaningful.is_(True), Signal.category != "internal")
    tot_records += cnt(RawItem, RawItem.document_id.is_(None))
    print(f"## {c.name} (id {c.id})")
    print(f"- primary interview questions: {cnt(InterviewQuestion, InterviewQuestion.is_followup.is_(False))}, follow-ups: {cnt(InterviewQuestion, InterviewQuestion.is_followup.is_(True))}, answered: {cnt(InterviewQuestion, InterviewQuestion.status == 'answered')}, skipped: {cnt(InterviewQuestion, InterviewQuestion.status == 'skipped')}")
    comps = db.scalars(select(Competitor).where(Competitor.company_id == c.id).order_by(Competitor.confidence.desc())).all()
    print(f"- competitors (not rejected): {sum(1 for x in comps if x.status != 'rejected')} -> {', '.join(x.name for x in comps if x.status != 'rejected')}; rejected in review: {', '.join(x.name for x in comps if x.status == 'rejected') or 'none'}")
    print(f"- approved sources: {sum(by_cat.values())} by category {by_cat}; pending: {cnt(Source, Source.approval_status == 'pending')}; rejected: {cnt(Source, Source.approval_status == 'rejected')}")
    print(f"- crawl runs: {cnt(CrawlRun)}, crawl log entries: {cnt(CrawlLog)}, failed fetches: {cnt(CrawlLog, CrawlLog.status.in_(['error', 'blocked_robots']))}")
    print(f"- collected evidence records (external): {cnt(RawItem, RawItem.document_id.is_(None))}; meaningful external signals: {meaningful_ext}; internal signals: {cnt(Signal, Signal.category == 'internal')}")
    print(f"- external signals with evidence URL: {cnt(Signal, Signal.category != 'internal', Signal.evidence_url.like('http%'))}/{cnt(Signal, Signal.category != 'internal')}")
    print(f"- briefs: {cnt(Brief)}, audits: {cnt(AuditReport)}, context changes: {cnt(ContextChange)}, documents: {cnt(InternalDocument)}")
    print(f"- job runs: {dict(db.execute(select(JobRun.status, func.count()).where(JobRun.company_id == c.id).group_by(JobRun.status)).all())}")
print(f"\nTOTAL external evidence records collected across companies: {tot_records}")
print(f"TOTAL meaningful external signals: {db.scalar(select(func.count()).select_from(Signal).where(Signal.is_meaningful.is_(True), Signal.category != 'internal'))}")
