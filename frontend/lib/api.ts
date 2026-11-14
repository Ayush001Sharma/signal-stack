import type {
  AnsweredBy,
  AnswerResult,
  Audit,
  Brief,
  BriefAction,
  BriefSummary,
  Company,
  CompanySummary,
  Competitor,
  ContextChange,
  CrawlLog,
  CrawlRun,
  Dashboard,
  Duplicate,
  Facets,
  Fact,
  FactStatus,
  InternalDocument,
  InterviewState,
  JobRun,
  JobStarted,
  Page,
  Question,
  RawItem,
  Schedule,
  ScheduleUpdate,
  SchedulerStatus,
  Signal,
  SignalDetail,
  SignalStack,
  Source,
  SystemInfo,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Turn a FastAPI error `detail` into a readable message (handles 422 arrays and 409 objects). */
export function describeDetail(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === "object" && "msg" in d) {
          const loc = Array.isArray((d as { loc?: unknown[] }).loc)
            ? ((d as { loc: unknown[] }).loc.filter((x) => x !== "body").join(".") as string)
            : "";
          return loc ? `${loc}: ${(d as { msg: string }).msg}` : (d as { msg: string }).msg;
        }
        return JSON.stringify(d);
      })
      .join("; ");
  }
  if (typeof detail === "object") {
    const o = detail as Record<string, unknown>;
    if (typeof o.message === "string") {
      const extra = o.name ? ` (“${String(o.name)}”, #${String(o.duplicate_of_id ?? "")})` : "";
      return o.message + extra;
    }
    return JSON.stringify(detail);
  }
  return String(detail);
}

/** Field-level errors from a 422 validation response, keyed by the last loc segment. */
export function fieldErrors(err: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (err instanceof ApiError && err.status === 422 && Array.isArray(err.detail)) {
    for (const d of err.detail as Array<{ loc?: unknown[]; msg?: string }>) {
      const key = Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : "form";
      if (d.msg) out[key] = d.msg;
    }
  }
  return out;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) {
    if (err.message === "Failed to fetch") return `Cannot reach the Signal Stack API at ${API_URL}. Is the backend running?`;
    return err.message;
  }
  return String(err);
}

export function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

type Query = Record<string, string | number | boolean | null | undefined>;

export function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${path}${path.includes("?") ? "&" : "?"}${s}` : path;
}

export async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (API_KEY) headers.set("X-API-Key", API_KEY);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  headers.set("Accept", headers.get("Accept") || "application/json");
  const res = await fetch(apiUrl(path), { ...init, headers, body });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      const data = await res.json();
      detail = (data as { detail?: unknown }).detail ?? data;
    } catch {
      detail = res.statusText;
    }
    const msg = describeDetail(detail) || `Request failed (${res.status})`;
    throw new ApiError(res.status, msg, detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

/** Download a binary/text export and trigger a browser save. */
export async function download(path: string, filename: string): Promise<void> {
  const headers = new Headers();
  if (API_KEY) headers.set("X-API-Key", API_KEY);
  const res = await fetch(apiUrl(path), { headers });
  if (!res.ok) throw new ApiError(res.status, `Export failed (${res.status})`, null);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const swrFetcher = <T,>(path: string) => request<T>(path);

const c = (id: number | string) => `/api/companies/${id}`;

// -------------------------------------------------------------------- endpoint paths (GET, for SWR keys)
export const paths = {
  companies: () => "/api/companies",
  company: (id: number | string) => c(id),
  facts: (id: number | string) => `${c(id)}/facts`,
  interview: (id: number | string) => `${c(id)}/interview`,
  competitors: (id: number | string) => `${c(id)}/competitors`,
  contextChanges: (id: number | string) => `${c(id)}/context-changes`,
  sources: (id: number | string, q?: Query) => withQuery(`${c(id)}/sources`, q),
  signalStack: (id: number | string) => `${c(id)}/signal-stack`,
  duplicates: (id: number | string) => `${c(id)}/sources/duplicates`,
  sourceHistory: (id: number | string, sid: number) => `${c(id)}/sources/${sid}/history`,
  sourceItems: (id: number | string, sid: number) => `${c(id)}/sources/${sid}/items`,
  crawlRuns: (id: number | string, q?: Query) => withQuery(`${c(id)}/crawl-runs`, q),
  crawlLogs: (id: number | string, q?: Query) => withQuery(`${c(id)}/crawl-logs`, q),
  signals: (id: number | string, q?: Query) => withQuery(`${c(id)}/signals`, q),
  signal: (id: number | string, sid: number) => `${c(id)}/signals/${sid}`,
  facets: (id: number | string) => `${c(id)}/signals-facets`,
  briefs: (id: number | string, q?: Query) => withQuery(`${c(id)}/briefs`, q),
  latestBrief: (id: number | string) => `${c(id)}/briefs/latest`,
  brief: (id: number | string, bid: number | string) => `${c(id)}/briefs/${bid}`,
  briefActions: (id: number | string, bid: number | string) => `${c(id)}/briefs/${bid}/actions`,
  briefMarkdown: (id: number | string, bid: number | string) => `${c(id)}/briefs/${bid}/markdown`,
  briefHtml: (id: number | string, bid: number | string) => `${c(id)}/briefs/${bid}/html`,
  briefPdf: (id: number | string, bid: number | string) => `${c(id)}/briefs/${bid}/pdf`,
  audits: (id: number | string) => `${c(id)}/audits`,
  audit: (id: number | string, aid: number | string) => `${c(id)}/audits/${aid}`,
  dashboard: (id: number | string) => `${c(id)}/dashboard`,
  jobs: (q?: Query) => withQuery(`/api/jobs`, q),
  job: (jid: number) => `/api/jobs/${jid}`,
  scheduler: () => "/api/scheduler",
  schedule: (id: number | string) => `${c(id)}/schedule`,
  documents: (id: number | string) => `${c(id)}/documents`,
  system: () => "/api/system",
};

// -------------------------------------------------------------------- typed calls
export const api = {
  listCompanies: () => request<CompanySummary[]>(paths.companies()),
  getCompany: (id: number) => request<Company>(paths.company(id)),
  createCompany: (body: { name: string; website: string; industry?: string | null; business_context?: string | null; run_setup?: boolean }) =>
    request<Company>(paths.companies(), { method: "POST", json: body }),
  updateCompany: (id: number, body: { name?: string; industry?: string | null; business_context?: string | null }) =>
    request<Company>(paths.company(id), { method: "PATCH", json: body }),
  deleteCompany: (id: number) => request<void>(paths.company(id), { method: "DELETE" }),
  rerunResearch: (id: number) => request<JobStarted>(`${c(id)}/research`, { method: "POST" }),
  rerunSetup: (id: number) => request<JobStarted>(`${c(id)}/setup`, { method: "POST" }),

  addFact: (id: number, body: { field: string; value: string; status?: FactStatus; source_url?: string | null; evidence?: string | null }) =>
    request<Fact>(paths.facts(id), { method: "POST", json: body }),
  updateFact: (id: number, fid: number, body: { value?: string; status?: FactStatus }) =>
    request<Fact>(`${paths.facts(id)}/${fid}`, { method: "PATCH", json: body }),
  deleteFact: (id: number, fid: number) => request<void>(`${paths.facts(id)}/${fid}`, { method: "DELETE" }),

  getInterview: (id: number) => request<InterviewState>(paths.interview(id)),
  generateInterview: (id: number) => request<Question[]>(`${c(id)}/interview/generate`, { method: "POST" }),
  answerQuestion: (id: number, qid: number, body: { answer?: string; skip?: boolean; confidential?: boolean; answered_by?: AnsweredBy }) =>
    request<AnswerResult>(`${c(id)}/interview/questions/${qid}/answer`, { method: "POST", json: body }),

  addCompetitor: (id: number, body: { name: string; website?: string | null; description?: string | null; kind?: "direct" | "substitute" }) =>
    request<Competitor>(paths.competitors(id), { method: "POST", json: body }),
  updateCompetitor: (id: number, cid: number, body: { status?: "suggested" | "confirmed" | "rejected"; website?: string; kind?: string; description?: string }) =>
    request<Competitor>(`${paths.competitors(id)}/${cid}`, { method: "PATCH", json: body }),
  discoverCompetitors: (id: number) => request<JobStarted>(`${c(id)}/competitors/discover`, { method: "POST" }),

  changeContext: (id: number, body: { industry?: string | null; business_context: string }) =>
    request<JobStarted>(`${c(id)}/context`, { method: "POST", json: body }),

  addSource: (
    id: number,
    body: { name: string; url: string; category: string; source_type: string; description?: string | null; reason: string; approve: boolean; competitor_id?: number | null },
  ) => request<Source>(`${c(id)}/sources`, { method: "POST", json: body }),
  updateSource: (id: number, sid: number, body: { approval_status?: string; monitoring_status?: string; name?: string; description?: string; reason?: string }) =>
    request<Source>(`${c(id)}/sources/${sid}`, { method: "PATCH", json: body }),
  removeSource: (id: number, sid: number) => request<void>(`${c(id)}/sources/${sid}`, { method: "DELETE" }),
  bulkSources: (id: number, action: string, source_ids: number[] = []) =>
    request<{ updated: number; action: string }>(`${c(id)}/sources/bulk`, { method: "POST", json: { action, source_ids } }),
  checkSource: (id: number, sid: number) => request<JobStarted>(`${c(id)}/sources/${sid}/check`, { method: "POST" }),
  discoverSources: (id: number) => request<JobStarted>(`${c(id)}/sources/discover`, { method: "POST" }),
  sourceHistory: (id: number, sid: number) => request<CrawlLog[]>(paths.sourceHistory(id, sid)),
  sourceItems: (id: number, sid: number) => request<RawItem[]>(paths.sourceItems(id, sid)),

  crawlNow: (id: number) => request<JobStarted>(`${c(id)}/crawl`, { method: "POST" }),

  updateSignal: (id: number, sid: number, status: "new" | "reviewed" | "dismissed") =>
    request<Signal>(paths.signal(id, sid), { method: "PATCH", json: { status } }),
  getSignal: (id: number, sid: number) => request<SignalDetail>(paths.signal(id, sid)),

  generateBrief: (id: number, body: { lookback_days?: number } = {}) => request<JobStarted>(`${c(id)}/briefs`, { method: "POST", json: body }),
  updateAction: (id: number, aid: number, body: { status?: string; owner?: string | null }) =>
    request<BriefAction>(`${c(id)}/actions/${aid}`, { method: "PATCH", json: body }),

  runAudit: (id: number) => request<JobStarted>(`${c(id)}/audits`, { method: "POST" }),

  getJob: (jid: number) => request<JobRun>(paths.job(jid)),
  putSchedule: (id: number, body: ScheduleUpdate) => request<Schedule>(paths.schedule(id), { method: "PUT", json: body }),

  uploadDocument: (id: number, file: File, description?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (description) fd.append("description", description);
    return request<InternalDocument>(paths.documents(id), { method: "POST", body: fd });
  },
  deleteDocument: (id: number, did: number) => request<void>(`${paths.documents(id)}/${did}`, { method: "DELETE" }),
};

export type {
  Audit,
  Brief,
  BriefAction,
  BriefSummary,
  ContextChange,
  CrawlRun,
  Dashboard,
  Duplicate,
  Facets,
  Page,
  SchedulerStatus,
  SignalStack,
  SystemInfo,
};
