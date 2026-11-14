// Types mirroring the Signal Stack FastAPI schemas (see docs-openapi.json).

export type Category = "customers" | "competitors" | "market" | "internal";
export const CATEGORIES: Category[] = ["customers", "competitors", "market", "internal"];

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface JobStarted {
  job_run_id: number;
  status: string;
}

export interface CompanySummary {
  id: number;
  name: string;
  website: string;
  industry: string | null;
  industry_label?: string | null;
  status: string;
  created_at: string;
}

export interface CompanyProfile {
  one_liner?: string | null;
  industry?: string | null;
  industry_confidence?: number;
  positioning?: string | null;
  products?: string[];
  customer_segments?: string[];
  geographies?: string[];
  business_model?: string[];
  meta_keywords?: string[];
  site_feeds?: string[];
  business_context?: string | null;
  founder?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ResearchSummary {
  pages_crawled?: string[];
  errors?: string[] | Array<Record<string, unknown>>;
  feeds_found?: string[];
  developments_found?: number;
  name_collisions_excluded?: Array<{ title: string; url: string; similarity: number }>;
  method?: { llm?: { available?: boolean; model?: string; provider?: string }; embeddings?: string };
  [key: string]: unknown;
}

export interface Company {
  id: number;
  name: string;
  website: string;
  domain: string;
  industry: string | null;
  industry_label?: string | null;
  business_context: string | null;
  status: string;
  profile: CompanyProfile;
  keywords: string[];
  research_summary: ResearchSummary;
  research_error: string | null;
  profile_version: number;
  created_at: string;
  updated_at: string;
}

export type FactStatus = "verified" | "unverified" | "assumption" | "needs_confirmation";
export const FACT_STATUSES: FactStatus[] = ["verified", "unverified", "assumption", "needs_confirmation"];

export interface Fact {
  id: number;
  field: string;
  value: string;
  status: FactStatus | string;
  origin: string;
  source_url: string | null;
  evidence: string | null;
  created_at: string;
  updated_at: string;
}

export interface Question {
  id: number;
  position: number;
  sort_key: number;
  topic: string;
  question: string;
  rationale: string | null;
  is_followup: boolean;
  parent_id: number | null;
  answer: string | null;
  status: "pending" | "answered" | "skipped" | string;
  confidential: boolean;
  generated_by: string;
  answered_at: string | null;
  answered_by?: AnsweredBy | string | null;
}

export type AnsweredBy = "founder" | "team_member" | "demo_operator";

export interface InterviewState {
  questions: Question[];
  next: Question | null;
  progress: { primary_total: number; answered: number; skipped: number; pending: number; followups: number };
  topic_labels: Record<string, string>;
  complete: boolean;
}

export interface AnswerChanges {
  facts?: string[];
  competitors_added?: string[];
  competitors_rejected?: string[];
  keywords_added?: string[];
  [key: string]: unknown;
}

export interface AnswerResult {
  question: Question;
  changes: AnswerChanges;
  followup_id: number | null;
  next: Question | null;
}

export interface CompetitorEvidence {
  title: string;
  url: string;
  publisher?: string | null;
  date?: string | null;
  query?: string;
}

export interface Competitor {
  id: number;
  name: string;
  website: string | null;
  description: string | null;
  kind: string;
  reason: string | null;
  evidence: CompetitorEvidence[];
  discovery_method: string;
  mention_count: number;
  confidence: number;
  status: "suggested" | "confirmed" | "rejected" | string;
  created_at: string;
}

export interface RelevanceChange {
  source_id: number;
  name: string;
  before: number;
  after: number;
  delta: number;
}

export interface ContextChange {
  id: number;
  company_id: number;
  old_context: { industry?: string | null; business_context?: string | null; keywords?: string[] };
  new_context: { industry?: string | null; business_context?: string | null; keywords?: string[] };
  added_keywords: string[];
  removed_keywords: string[];
  relevance_changes: RelevanceChange[];
  flagged_sources: Array<{ source_id: number; name: string; why: string }>;
  new_source_ids: number[];
  summary: string;
  created_at: string;
}

export interface SampleItem {
  title: string;
  url?: string | null;
  date?: string | null;
}

export interface Source {
  id: number;
  company_id: number;
  competitor_id: number | null;
  name: string;
  url: string;
  category: Category | string;
  source_type: string;
  description: string | null;
  reason: string | null;
  query: string | null;
  credibility: number;
  credibility_label: string;
  credibility_rationale: string | null;
  expected_relevance: number;
  relevance_rationale: string | null;
  update_frequency: string;
  approval_status: "pending" | "approved" | "rejected" | "removed" | string;
  recommended: boolean;
  monitoring_status: "active" | "paused" | string;
  health_status: string;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_new_item_at: string | null;
  consecutive_failures: number;
  last_error: string | null;
  duplicate_of_id: number | null;
  discovered_by: string;
  sample_items: SampleItem[];
  created_at: string;
  competitor_name?: string | null;
}

export interface StackDocument {
  id: number;
  filename: string;
  status: string;
  records: number;
  uploaded_at: string;
}

export interface StackColumn {
  sources: Source[];
  approved: number;
  pending: number;
  documents?: StackDocument[];
}

export type SignalStack = Record<Category, StackColumn>;

export interface Duplicate {
  source_id: number;
  name: string;
  url: string;
  duplicate_of_id: number;
  duplicate_of_name: string;
}

export interface CrawlLog {
  id: number;
  source_id: number;
  crawl_run_id: number | null;
  started_at: string;
  duration_ms: number;
  status: string;
  http_status: number | null;
  items_found: number;
  new_items: number;
  changed_items: number;
  error: string | null;
}

export interface CrawlRun {
  id: number;
  company_id: number;
  job_run_id: number | null;
  trigger: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  sources_checked: number;
  sources_failed: number;
  items_seen: number;
  new_items: number;
  changed_items: number;
  duplicates_skipped: number;
  signals_created: number;
  message: string | null;
}

export interface RawItem {
  id: number;
  source_id: number | null;
  url: string;
  title: string;
  snippet: string | null;
  publisher: string | null;
  published_at: string | null;
  discovered_at: string;
  version: number;
  item_type: string;
  duplicate_of_id: number | null;
  date_source: string;
}

export interface ScoreBreakdown {
  weights?: Record<string, number>;
  components?: Record<string, number>;
  reasons?: Record<string, string>;
  formula?: string;
  thresholds?: Record<string, number>;
  rule_interpretation?: { why?: string; action?: string };
  [key: string]: unknown;
}

export interface Signal {
  id: number;
  company_id: number;
  raw_item_id: number | null;
  source_id: number | null;
  competitor_id: number | null;
  document_id: number | null;
  category: Category | string;
  signal_type: string;
  title: string;
  what_happened: string;
  event_date: string | null;
  discovered_at: string;
  evidence_url: string | null;
  evidence_snippet: string | null;
  publisher: string | null;
  verification_status: string;
  source_reliability: number;
  evidence_strength: number;
  relevance: number;
  impact: number;
  urgency: number;
  novelty: number;
  recency: number;
  priority_score: number;
  priority: "high" | "medium" | "low" | string;
  score_breakdown: ScoreBreakdown;
  polarity: "opportunity" | "threat" | "neutral" | string;
  business_area: string;
  sentiment: number | null;
  why_it_matters: string | null;
  recommended_action: string | null;
  interpretation_method: string;
  ai_confidence: number | null;
  is_meaningful: boolean;
  materiality: string;
  corroboration_count: number;
  status: "new" | "reviewed" | "dismissed" | string;
  source_name?: string | null;
  competitor_name?: string | null;
}

export interface SignalDetail {
  signal: Signal;
  raw_evidence: {
    id: number;
    url: string;
    title: string;
    snippet: string | null;
    content: string;
    publisher: string | null;
    published_at: string | null;
    discovered_at: string;
    version: number;
    item_type: string;
    date_source: string;
    extra: Record<string, unknown> | null;
  } | null;
}

export interface Facets {
  category: Record<string, number>;
  priority: Record<string, number>;
  polarity: Record<string, number>;
  verification_status: Record<string, number>;
  signal_type: Record<string, number>;
  competitors: Array<{ id: number; name: string }>;
  total_collected: number;
  raw_items: number;
}

export interface BriefStats {
  lookback_days?: number;
  meaningful_signals?: number;
  by_category?: Record<string, number>;
  internal_signals?: number;
  approved_sources?: number;
  last_crawl?: { started: string; status: string; message: string | null } | null;
  high_priority?: number;
  opportunities?: number;
  risks?: number;
}

export interface BriefSummary {
  id: number;
  company_id: number;
  title: string;
  period_start: string;
  period_end: string;
  trigger: string;
  stats: BriefStats;
  generated_at: string;
}

export interface BriefItem {
  ref: string;
  signal_id: number;
  title: string;
  category: string;
  type: string;
  what_happened: string;
  when: string | null;
  discovered: string | null;
  publisher: string | null;
  evidence_url: string | null;
  evidence: string | null;
  verification: string;
  source_reliability: number;
  evidence_strength: number;
  relevance: number;
  impact: number;
  urgency: number;
  priority: string;
  priority_score: number;
  polarity: string;
  business_area: string;
  why_it_matters: string | null;
  recommended_action: string | null;
  interpretation: string;
  competitor: string | null;
  materiality: string;
  score_reasons?: Record<string, string>;
  next_step?: string | null;
}

export interface BriefAppendixRow {
  ref: string;
  title: string;
  source: string | null;
  url: string | null;
  published: string;
  discovered: string | null;
  snippet: string | null;
  verification: string;
  source_reliability: number;
  evidence_strength: number;
  strategic_relevance: number;
  interpretation: string;
}

export interface BriefContent {
  company: { id: number; name: string; website: string; industry: string | null };
  period: { start: string; end: string };
  generated_at: string;
  executive_summary: BriefItem[];
  customer_signals: {
    items: BriefItem[];
    themes: Array<{ type: string; count: number }>;
    average_sentiment: number | null;
    empty_message: string | null;
  };
  competitor_intelligence: { groups: Array<{ competitor: string; items: BriefItem[] }>; empty_message: string | null };
  market_intelligence: { material: BriefItem[]; general: BriefItem[]; empty_message: string | null };
  internal_intelligence: {
    items: BriefItem[];
    documents: Array<{ id: number; filename: string; records: number; uploaded: string; description: string | null; synthetic?: boolean }>;
    empty_message: string | null;
    synthetic_note?: string | null;
  };
  opportunities: BriefItem[];
  opportunities_note: string | null;
  risks: BriefItem[];
  risks_note: string | null;
  recommended_actions: Array<{ action: string; reason: string; owner: string; priority: string; signal_id: number }>;
  watch_list: Array<{ title: string; why: string; ref: string | null; url: string | null }>;
  source_appendix: BriefAppendixRow[];
  narrative: { text: string; method: string };
  methodology: { ranking: string; evidence_policy: string; window: string };
}

export interface Brief extends BriefSummary {
  content: BriefContent;
  markdown: string;
}

export type ActionStatus = "open" | "in_progress" | "done" | "dismissed";

export interface BriefAction {
  id: number;
  brief_id: number;
  signal_id: number | null;
  action: string;
  reason: string | null;
  owner: string | null;
  priority: string;
  status: ActionStatus | string;
  updated_at: string;
}

export interface AuditContent {
  generated_at: string;
  summary: Record<string, number>;
  availability: Array<{ source_id: number; name: string; ok: boolean; status: number | null; error: string | null }>;
  dead: Array<{ source_id: number; name: string; ok: boolean; status: number | null; error: string | null }>;
  duplicates: Array<{ source_id: number; duplicate_of: number }>;
  inactive: Array<{ source_id: number; name: string; latest_item: string | null }>;
  declining: Array<{ source_id: number; name: string; reason: string; current_relevance: number | null }>;
  current_relevance: Record<string, number>;
  recommend_add: Array<{ source_id: number; name: string; category: string; why: string | null; expected_relevance: number }>;
  recommend_remove: Array<{ source_id: number; name: string; why: string }>;
  discovery: Record<string, unknown> | null;
}

export interface Audit {
  id: number;
  company_id: number;
  trigger: string;
  content: AuditContent;
  markdown: string;
  generated_at: string;
}

export interface JobRun {
  id: number;
  company_id: number | null;
  job_type: string;
  trigger: string;
  status: "queued" | "running" | "success" | "partial" | "failed" | string;
  started_at: string;
  finished_at: string | null;
  message: string | null;
  error: string | null;
  details: Record<string, unknown>;
}

export interface ScheduledJob {
  id: string;
  name: string;
  job_type: string;
  company_id: number;
  next_run_time: string | null;
  trigger: string;
}

export interface SchedulerStatus {
  running: boolean;
  jobs: ScheduledJob[];
}

export interface Schedule {
  company_id: number;
  timezone: string;
  weekly_enabled: boolean;
  weekly_day_of_week: string;
  weekly_time: string;
  monthly_enabled: boolean;
  monthly_day: number;
  monthly_time: string;
  crawl_enabled: boolean;
  crawl_interval_hours: number;
  brief_lookback_days: number;
  updated_at: string;
}

export type ScheduleUpdate = Partial<Omit<Schedule, "company_id" | "updated_at">>;

export interface DocumentTheme {
  label: string;
  title: string;
  count: number;
  detail?: string;
  quotes: Array<{ text: string; ref: string }>;
}

export interface InternalDocument {
  id: number;
  company_id: number;
  filename: string;
  content_type: string;
  file_type: string;
  size_bytes: number;
  sha256: string;
  description: string | null;
  status: string;
  error: string | null;
  record_count: number;
  insights: { labels?: Record<string, number>; themes?: DocumentTheme[]; unlabelled_records?: number };
  uploaded_at: string;
}

export interface Dashboard {
  company: CompanySummary;
  sources: { approved: number; pending: number; health: Record<string, number>; by_category: Record<string, number> };
  signals: {
    total_meaningful: number;
    new_this_week: number;
    high_priority: number;
    opportunities: number;
    risks: number;
    by_category: Record<string, number>;
    raw_items: number;
  };
  latest_brief: BriefSummary | null;
  recent_activity: Array<{ kind: string; at: string; status: string; message: string | null }>;
  upcoming_jobs: ScheduledJob[];
  signal_trend: Array<{ date: string; customers: number; competitors: number; market: number; internal: number }>;
  top_signals: Signal[];
  failed_jobs: JobRun[];
}

export interface SystemInfo {
  app: string;
  environment: string;
  llm: { provider?: string; model?: string; url?: string; available?: boolean; [k: string]: unknown };
  embeddings: string;
  scheduler: { enabled: boolean; running: boolean };
  auth: string;
  crawler: {
    user_agent: string;
    per_host_delay_seconds: number;
    timeout_seconds: number;
    max_retries: number;
    respects_robots_txt: boolean;
  };
  reddit_api_configured: boolean;
  upload_limit_mb: number;
  counts: Record<string, number>;
}
