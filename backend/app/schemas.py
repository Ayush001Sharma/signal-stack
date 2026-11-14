"""Pydantic request/response schemas (validation + OpenAPI documentation)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------- companies
class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    website: HttpUrl
    industry: str | None = Field(default=None, max_length=200)
    business_context: str | None = Field(default=None, max_length=4000)
    run_setup: bool = True

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    industry: str | None = Field(default=None, max_length=200)
    business_context: str | None = Field(default=None, max_length=4000)
    profile: dict | None = None


class ContextChangeRequest(BaseModel):
    """industry: None = unchanged, "" = clear. business_context: "" clears the context (reverts to research-only themes)."""

    industry: str | None = Field(default=None, max_length=200)
    business_context: str = Field(max_length=4000)

    @field_validator("business_context")
    @classmethod
    def _ctx(cls, v: str) -> str:
        v = v.strip()
        if v and len(v) < 10:
            raise ValueError("business_context must be empty (to clear) or at least 10 characters")
        return v


class CompanyOut(ORM):
    id: int
    name: str
    website: str
    domain: str
    industry: str | None
    industry_label: str | None = None
    business_context: str | None
    status: str
    profile: dict
    keywords: list
    research_summary: dict
    research_error: str | None
    profile_version: int
    created_at: datetime
    updated_at: datetime


class CompanySummary(ORM):
    id: int
    name: str
    website: str
    industry: str | None
    industry_label: str | None = None
    status: str
    created_at: datetime


class FactOut(ORM):
    id: int
    field: str
    value: str
    status: str
    origin: str
    source_url: str | None
    evidence: str | None
    created_at: datetime
    updated_at: datetime


FactStatusLiteral = Literal["verified", "unverified", "assumption", "needs_confirmation"]


class FactCreate(BaseModel):
    field: str = Field(min_length=2, max_length=60, pattern=r"^[a-z_]+$")
    value: str = Field(min_length=1, max_length=2000)
    status: FactStatusLiteral = "verified"
    source_url: str | None = Field(default=None, max_length=1000)
    evidence: str | None = Field(default=None, max_length=1500)


class FactUpdate(BaseModel):
    value: str | None = Field(default=None, min_length=1, max_length=2000)
    status: FactStatusLiteral | None = None


# ---------------------------------------------------------------- interview
class QuestionOut(ORM):
    id: int
    position: int
    sort_key: float
    topic: str
    question: str
    rationale: str | None
    is_followup: bool
    parent_id: int | None
    answer: str | None
    status: str
    confidential: bool
    answered_by: str | None = None
    generated_by: str
    answered_at: datetime | None


class AnswerIn(BaseModel):
    answer: str | None = Field(default=None, max_length=5000)
    skip: bool = False
    confidential: bool = False
    answered_by: Literal["founder", "team_member", "demo_operator"] = "founder"

    @field_validator("answer")
    @classmethod
    def _clean(cls, v):
        return v.strip() if isinstance(v, str) else v


# ---------------------------------------------------------------- competitors
class CompetitorOut(ORM):
    id: int
    name: str
    website: str | None
    description: str | None
    kind: str
    reason: str | None
    evidence: list
    discovery_method: str
    mention_count: int
    confidence: float
    status: str
    created_at: datetime


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    website: HttpUrl | None = None
    description: str | None = Field(default=None, max_length=1000)
    kind: Literal["direct", "substitute"] = "direct"


class CompetitorUpdate(BaseModel):
    status: Literal["suggested", "confirmed", "rejected"] | None = None
    website: HttpUrl | None = None
    kind: Literal["direct", "substitute"] | None = None
    description: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------- sources
SourceType = Literal["rss", "news_search", "web_page", "stackexchange", "hackernews", "federal_register", "govuk", "reddit"]
CategoryLiteral = Literal["customers", "competitors", "market", "internal"]


class SourceOut(ORM):
    id: int
    company_id: int
    competitor_id: int | None
    name: str
    url: str
    category: str
    source_type: str
    description: str | None
    reason: str | None
    query: str | None
    credibility: float
    credibility_label: str
    credibility_rationale: str | None
    expected_relevance: float
    relevance_rationale: str | None
    update_frequency: str
    approval_status: str
    recommended: bool
    monitoring_status: str
    health_status: str
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_new_item_at: datetime | None
    consecutive_failures: int
    last_error: str | None
    duplicate_of_id: int | None
    discovered_by: str
    sample_items: list
    created_at: datetime


class SourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    url: HttpUrl
    category: CategoryLiteral
    source_type: SourceType = "rss"
    description: str | None = Field(default=None, max_length=1000)
    reason: str = Field(min_length=5, max_length=1000)
    competitor_id: int | None = None
    config: dict = Field(default_factory=dict)
    approve: bool = True


class SourceUpdate(BaseModel):
    approval_status: Literal["pending", "approved", "rejected"] | None = None
    monitoring_status: Literal["active", "paused"] | None = None
    name: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=1000)


class BulkSourceAction(BaseModel):
    source_ids: list[int] = Field(default_factory=list, max_length=500)
    action: Literal["approve", "reject", "pause", "resume", "remove", "approve_recommended"]


class CrawlLogOut(ORM):
    id: int
    source_id: int
    crawl_run_id: int | None
    started_at: datetime
    duration_ms: int
    status: str
    http_status: int | None
    items_found: int
    new_items: int
    changed_items: int
    error: str | None


class CrawlRunOut(ORM):
    id: int
    company_id: int
    job_run_id: int | None
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    sources_checked: int
    sources_failed: int
    items_seen: int
    new_items: int
    changed_items: int
    duplicates_skipped: int
    signals_created: int
    message: str | None


class RawItemOut(ORM):
    id: int
    source_id: int | None
    url: str
    title: str
    snippet: str | None
    publisher: str | None
    published_at: datetime | None
    discovered_at: datetime
    version: int
    item_type: str
    duplicate_of_id: int | None
    date_source: str


# ---------------------------------------------------------------- signals
class SignalOut(ORM):
    id: int
    company_id: int
    raw_item_id: int | None
    source_id: int | None
    competitor_id: int | None
    document_id: int | None
    category: str
    signal_type: str
    title: str
    what_happened: str
    event_date: datetime | None
    discovered_at: datetime
    evidence_url: str | None
    evidence_snippet: str | None
    publisher: str | None
    verification_status: str
    source_reliability: float
    evidence_strength: float
    relevance: float
    impact: float
    urgency: float
    novelty: float
    recency: float
    priority_score: float
    priority: str
    score_breakdown: dict
    polarity: str
    business_area: str
    sentiment: float | None
    why_it_matters: str | None
    recommended_action: str | None
    interpretation_method: str
    ai_confidence: float | None
    is_meaningful: bool
    materiality: str
    corroboration_count: int
    status: str
    source_name: str | None = None
    competitor_name: str | None = None


class SignalUpdate(BaseModel):
    status: Literal["new", "reviewed", "dismissed"]


# ---------------------------------------------------------------- briefs / audits / jobs
class BriefSummary(ORM):
    id: int
    company_id: int
    title: str
    period_start: datetime
    period_end: datetime
    trigger: str
    stats: dict
    generated_at: datetime


class BriefOut(BriefSummary):
    content: dict
    markdown: str


class BriefActionOut(ORM):
    id: int
    brief_id: int
    signal_id: int | None
    action: str
    reason: str | None
    owner: str | None
    priority: str
    status: str
    updated_at: datetime


class BriefActionUpdate(BaseModel):
    status: Literal["open", "in_progress", "done", "dismissed"] | None = None
    owner: str | None = Field(default=None, max_length=100)


class BriefRequest(BaseModel):
    lookback_days: int | None = Field(default=None, ge=1, le=120)
    crawl: bool = True
    use_llm: bool = True


class AuditOut(ORM):
    id: int
    company_id: int
    trigger: str
    content: dict
    markdown: str
    generated_at: datetime


class ContextChangeOut(ORM):
    id: int
    company_id: int
    old_context: dict
    new_context: dict
    added_keywords: list
    removed_keywords: list
    relevance_changes: list
    flagged_sources: list
    new_source_ids: list
    summary: str
    created_at: datetime


class JobRunOut(ORM):
    id: int
    company_id: int | None
    job_type: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    message: str | None
    error: str | None
    details: dict


class JobStarted(BaseModel):
    job_run_id: int
    status: str = "queued"


class DocumentOut(ORM):
    id: int
    company_id: int
    filename: str
    content_type: str
    file_type: str
    size_bytes: int
    sha256: str
    description: str | None
    status: str
    error: str | None
    record_count: int
    insights: dict
    uploaded_at: datetime


TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleOut(ORM):
    company_id: int
    timezone: str
    weekly_enabled: bool
    weekly_day_of_week: str
    weekly_time: str
    monthly_enabled: bool
    monthly_day: int
    monthly_time: str
    crawl_enabled: bool
    crawl_interval_hours: int
    brief_lookback_days: int
    updated_at: datetime


class ScheduleUpdate(BaseModel):
    timezone: str | None = None
    weekly_enabled: bool | None = None
    weekly_day_of_week: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] | None = None
    weekly_time: str | None = None
    monthly_enabled: bool | None = None
    monthly_day: int | None = Field(default=None, ge=1, le=28)
    monthly_time: str | None = None
    crawl_enabled: bool | None = None
    crawl_interval_hours: int | None = Field(default=None, ge=1, le=168)
    brief_lookback_days: int | None = Field(default=None, ge=1, le=120)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone '{v}'") from exc
        return v

    @field_validator("weekly_time", "monthly_time")
    @classmethod
    def _time(cls, v):
        if v is not None and not TIME_RE.match(v):
            raise ValueError("Time must be HH:MM (24h)")
        return v


class DashboardOut(BaseModel):
    company: CompanySummary
    sources: dict[str, Any]
    signals: dict[str, Any]
    latest_brief: BriefSummary | None
    recent_activity: list[dict]
    upcoming_jobs: list[dict]
    signal_trend: list[dict]
    top_signals: list[SignalOut]
    failed_jobs: list[JobRunOut]
