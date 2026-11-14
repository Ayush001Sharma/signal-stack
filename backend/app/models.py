"""SQLAlchemy ORM models for Signal Stack.

Every company-owned table carries ``company_id`` so data stays isolated per company.
Evidence (RawItem) is stored separately from interpretation (Signal) so analysis can be audited.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(str, enum.Enum):
    customers = "customers"
    competitors = "competitors"
    market = "market"
    internal = "internal"


class FactStatus(str, enum.Enum):
    verified = "verified"  # directly supported by a cited source or stated by the founder
    unverified = "unverified"  # reported by a third party, not confirmed
    assumption = "assumption"  # inferred by the system (rules or AI)
    needs_confirmation = "needs_confirmation"  # requires founder confirmation


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(String(500))
    domain: Mapped[str] = mapped_column(String(255), index=True)
    industry: Mapped[str | None] = mapped_column(String(200))
    business_context: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="created")  # created|researching|researched|interviewing|configured|error
    profile: Mapped[dict] = mapped_column(JSON, default=dict)  # structured profile summary
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    research_summary: Mapped[dict] = mapped_column(JSON, default=dict)  # pages crawled, errors, method
    research_error: Mapped[str | None] = mapped_column(Text)
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    facts: Mapped[list[ProfileFact]] = relationship(back_populates="company", cascade="all, delete-orphan")
    sources: Mapped[list[Source]] = relationship(back_populates="company", cascade="all, delete-orphan")
    competitors: Mapped[list[Competitor]] = relationship(back_populates="company", cascade="all, delete-orphan")
    schedule: Mapped[ScheduleConfig | None] = relationship(back_populates="company", cascade="all, delete-orphan", uselist=False)

    @property
    def industry_label(self) -> str | None:
        """User-provided industry, else the researched classification marked as inferred."""
        if self.industry:
            return self.industry
        inferred = (self.profile or {}).get("industry")
        return f"{inferred} (inferred)" if inferred else None


class ProfileFact(Base):
    """One atomic statement about the company with its provenance and verification status."""

    __tablename__ = "profile_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(60), index=True)  # business_model|products|customer_segments|positioning|industry|geographies|developments|revenue_streams|...
    value: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default=FactStatus.assumption.value)
    origin: Mapped[str] = mapped_column(String(30), default="research")  # research|interview|ai|user|news
    source_url: Mapped[str | None] = mapped_column(String(1000))
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship(back_populates="facts")


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)  # ordering; follow-ups use parent position + 0.x via sort_key
    sort_key: Mapped[float] = mapped_column(Float)
    topic: Mapped[str] = mapped_column(String(60))
    question: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)  # why this question was generated (research grounding)
    is_followup: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"))
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|answered|skipped
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    answered_by: Mapped[str | None] = mapped_column(String(30))  # founder|team_member|demo_operator
    generated_by: Mapped[str] = mapped_column(String(20), default="rules")  # rules|llm
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Competitor(Base):
    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("company_id", "name_key", name="uq_competitor_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default="direct")  # direct|substitute
    reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # [{title,url,publisher,date}]
    discovery_method: Mapped[str] = mapped_column(String(120), default="news_cooccurrence")
    mention_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(20), default="suggested")  # suggested|confirmed|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship(back_populates="competitors")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_company_norm", "company_id", "normalized_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    competitor_id: Mapped[int | None] = mapped_column(ForeignKey("competitors.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1500))
    normalized_url: Mapped[str] = mapped_column(String(1500))
    category: Mapped[str] = mapped_column(String(20), index=True)
    source_type: Mapped[str] = mapped_column(String(30))  # rss|news_search|gdelt|web_page|stackexchange|hackernews|federal_register|govuk|reddit
    description: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(String(500))  # search-based sources
    credibility: Mapped[float] = mapped_column(Float, default=0.5)
    credibility_label: Mapped[str] = mapped_column(String(40), default="medium")
    credibility_rationale: Mapped[str | None] = mapped_column(Text)
    expected_relevance: Mapped[float] = mapped_column(Float, default=0.5)
    relevance_rationale: Mapped[str | None] = mapped_column(Text)
    update_frequency: Mapped[str] = mapped_column(String(40), default="unknown")
    approval_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected|removed
    recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    monitoring_status: Mapped[str] = mapped_column(String(20), default="active")  # active|paused
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")  # unknown|healthy|degraded|failing|dead
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_new_item_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(String(300))
    last_modified: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str | None] = mapped_column(String(64))  # for web_page change detection
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    discovered_by: Mapped[str] = mapped_column(String(40), default="discovery")  # discovery|user|audit|context_change
    sample_items: Mapped[list] = mapped_column(JSON, default=list)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship(back_populates="sources")
    competitor: Mapped[Competitor | None] = relationship(foreign_keys=[competitor_id])


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_run_id: Mapped[int | None] = mapped_column(ForeignKey("job_runs.id", ondelete="SET NULL"))
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|partial|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sources_checked: Mapped[int] = mapped_column(Integer, default=0)
    sources_failed: Mapped[int] = mapped_column(Integer, default=0)
    items_seen: Mapped[int] = mapped_column(Integer, default=0)
    new_items: Mapped[int] = mapped_column(Integer, default=0)
    changed_items: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    signals_created: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)


class CrawlLog(Base):
    """Per-source fetch attempt — the crawl history shown in the Source Manager."""

    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    crawl_run_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))  # success|not_modified|error|blocked_robots|skipped
    http_status: Mapped[int | None] = mapped_column(Integer)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    new_items: Mapped[int] = mapped_column(Integer, default=0)
    changed_items: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class RawItem(Base):
    """Normalized evidence record exactly as collected (title/text/link/dates). Never edited by analysis."""

    __tablename__ = "raw_items"
    __table_args__ = (UniqueConstraint("company_id", "url_hash", "content_hash", name="uq_item_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("internal_documents.id", ondelete="CASCADE"), index=True)
    crawl_run_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_runs.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(String(2000))
    url_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(300))
    author: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    date_source: Mapped[str] = mapped_column(String(30), default="feed")  # feed|html_meta|jsonld|unknown
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    title_key: Mapped[str] = mapped_column(String(300), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # >1 => modified content at same URL
    item_type: Mapped[str] = mapped_column(String(30), default="article")  # article|post|question|page_change|page_snapshot|filing|internal_record|review
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("raw_items.id", ondelete="SET NULL"))
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class Signal(Base):
    """Analysis of one RawItem (or cluster of internal records): interpretation + explainable scores."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    raw_item_id: Mapped[int | None] = mapped_column(ForeignKey("raw_items.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), index=True)
    competitor_id: Mapped[int | None] = mapped_column(ForeignKey("competitors.id", ondelete="SET NULL"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("internal_documents.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(20), index=True)
    signal_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(Text)
    what_happened: Mapped[str] = mapped_column(Text)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    evidence_url: Mapped[str | None] = mapped_column(String(2000))
    evidence_snippet: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(300))
    verification_status: Mapped[str] = mapped_column(String(40))  # official_primary|corroborated|single_source_report|community_claim|internal_document|page_change
    # Separate measures (0..1)
    source_reliability: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_strength: Mapped[float] = mapped_column(Float, default=0.5)
    relevance: Mapped[float] = mapped_column(Float, default=0.0)  # strategic relevance
    impact: Mapped[float] = mapped_column(Float, default=0.0)
    urgency: Mapped[float] = mapped_column(Float, default=0.0)
    novelty: Mapped[float] = mapped_column(Float, default=1.0)
    recency: Mapped[float] = mapped_column(Float, default=0.0)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="low")  # high|medium|low
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    polarity: Mapped[str] = mapped_column(String(15), default="neutral")  # opportunity|threat|neutral
    business_area: Mapped[str] = mapped_column(String(60), default="Strategy")
    sentiment: Mapped[float | None] = mapped_column(Float)
    why_it_matters: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    interpretation_method: Mapped[str] = mapped_column(String(20), default="rules")  # rules|llm
    ai_confidence: Mapped[float | None] = mapped_column(Float)  # never used as proof
    is_meaningful: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    materiality: Mapped[str] = mapped_column(String(20), default="general")  # material|general
    corroboration_count: Mapped[int] = mapped_column(Integer, default=1)
    cluster_key: Mapped[str | None] = mapped_column(String(300), index=True)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new|reviewed|dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InternalDocument(Base):
    __tablename__ = "internal_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(600))
    content_type: Mapped[str] = mapped_column(String(100))
    file_type: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing|processed|error
    error: Mapped[str | None] = mapped_column(Text)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    insights: Mapped[dict] = mapped_column(JSON, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_run_id: Mapped[int | None] = mapped_column(ForeignKey("job_runs.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BriefAction(Base):
    """Action tracking for recommended actions in a brief."""

    __tablename__ = "brief_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("briefs.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|in_progress|done|dismissed
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditReport(Base):
    __tablename__ = "audit_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_run_id: Mapped[int | None] = mapped_column(ForeignKey("job_runs.id", ondelete="SET NULL"))
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ContextChange(Base):
    """Records a business-context update and how the Signal Stack was reassessed."""

    __tablename__ = "context_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    old_context: Mapped[dict] = mapped_column(JSON, default=dict)
    new_context: Mapped[dict] = mapped_column(JSON, default=dict)
    added_keywords: Mapped[list] = mapped_column(JSON, default=list)
    removed_keywords: Mapped[list] = mapped_column(JSON, default=list)
    relevance_changes: Mapped[list] = mapped_column(JSON, default=list)
    flagged_sources: Mapped[list] = mapped_column(JSON, default=list)
    new_source_ids: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(40), index=True)  # weekly_brief|monthly_audit|crawl|research|discovery|full_setup
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual|scheduled|startup_recovery
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)  # queued|running|success|partial|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class ScheduleConfig(Base):
    __tablename__ = "schedule_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    weekly_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    weekly_day_of_week: Mapped[str] = mapped_column(String(3), default="mon")
    weekly_time: Mapped[str] = mapped_column(String(5), default="07:00")
    monthly_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly_day: Mapped[int] = mapped_column(Integer, default=1)
    monthly_time: Mapped[str] = mapped_column(String(5), default="06:00")
    crawl_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    crawl_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    brief_lookback_days: Mapped[int] = mapped_column(Integer, default=14)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship(back_populates="schedule")
