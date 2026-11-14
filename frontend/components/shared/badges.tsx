import { Badge, type BadgeTone } from "@/components/ui/badge";
import { humanize } from "@/lib/utils";
import { CheckCircle2, CircleDashed, CircleHelp, Sparkles, ShieldCheck, AlertTriangle, Loader2, XCircle, Clock, MinusCircle } from "lucide-react";

export const PRIORITY_TONE: Record<string, BadgeTone> = { high: "rose", medium: "amber", low: "slate" };
export const POLARITY_TONE: Record<string, BadgeTone> = { opportunity: "emerald", threat: "rose", neutral: "slate" };
export const VERIFICATION_TONE: Record<string, BadgeTone> = {
  official_primary: "blue",
  primary_source: "blue",
  observed_change: "blue",
  page_change: "blue",
  internal_document: "emerald",
  corroborated: "emerald",
  single_source_report: "amber",
  community_claim: "orange",
};
export const VERIFICATION_LABEL: Record<string, string> = {
  official_primary: "Official primary",
  primary_source: "Primary source",
  corroborated: "Corroborated",
  single_source_report: "Single-source report",
  community_claim: "Community claim",
  observed_change: "Observed change",
  page_change: "Observed change",
  internal_document: "Internal document",
};
export const VERIFICATION_HELP: Record<string, string> = {
  official_primary: "Verified — published by an official primary source.",
  primary_source: "Self-published by the organisation itself.",
  corroborated: "Corroborated by multiple independent publishers.",
  single_source_report: "Reported by a single publisher — unconfirmed.",
  community_claim: "Community post — anecdotal and unverified.",
  observed_change: "A change directly observed on a monitored page.",
  page_change: "A change directly observed on a monitored page.",
  internal_document: "From an internal document you uploaded.",
};
export const CATEGORY_TONE: Record<string, BadgeTone> = { customers: "blue", competitors: "violet", market: "amber", internal: "emerald" };
export const CATEGORY_LABEL: Record<string, string> = { customers: "Customers", competitors: "Competitors", market: "Market", internal: "Internal" };
export const CATEGORY_COLOR: Record<string, string> = { customers: "#38bdf8", competitors: "#a78bfa", market: "#fbbf24", internal: "#34d399" };

export const HEALTH_TONE: Record<string, BadgeTone> = { healthy: "emerald", degraded: "amber", failing: "orange", dead: "rose", blocked: "rose", unknown: "slate" };
export const HEALTH_COLOR: Record<string, string> = { healthy: "#34d399", degraded: "#fbbf24", failing: "#fb923c", dead: "#f43f5e", blocked: "#e11d48", unknown: "#64748b" };

export function PriorityBadge({ priority, score }: { priority: string; score?: number }) {
  return (
    <Badge tone={PRIORITY_TONE[priority] ?? "slate"} title={`Priority ${priority}${score !== undefined ? ` (score ${Math.round(score)}/100)` : ""}`}>
      {humanize(priority)}
      {score !== undefined ? <span className="tabular-nums opacity-80">· {Math.round(score)}</span> : null}
    </Badge>
  );
}

export function PolarityBadge({ polarity }: { polarity: string }) {
  return <Badge tone={POLARITY_TONE[polarity] ?? "slate"}>{humanize(polarity)}</Badge>;
}

export function VerificationBadge({ status, label }: { status: string; label?: string }) {
  const tone = VERIFICATION_TONE[status] ?? "slate";
  return (
    <Badge tone={tone} title={VERIFICATION_HELP[status] ?? label ?? status}>
      <ShieldCheck className="h-3 w-3" aria-hidden />
      {label ?? VERIFICATION_LABEL[status] ?? humanize(status)}
    </Badge>
  );
}

/** Maps a human verification label from brief content back to a tone. */
export function verificationToneFromLabel(label: string): BadgeTone {
  const l = label.toLowerCase();
  if (l.includes("official") || l.includes("primary") || l.includes("observed")) return "blue";
  if (l.includes("corroborated") || l.includes("internal")) return "emerald";
  if (l.includes("single")) return "amber";
  if (l.includes("community")) return "orange";
  return "slate";
}

export function CategoryBadge({ category }: { category: string }) {
  return <Badge tone={CATEGORY_TONE[category] ?? "slate"}>{CATEGORY_LABEL[category] ?? humanize(category)}</Badge>;
}

const FACT_META: Record<string, { tone: BadgeTone; label: string; Icon: typeof CheckCircle2 }> = {
  verified: { tone: "emerald", label: "Verified", Icon: CheckCircle2 },
  unverified: { tone: "amber", label: "Unverified", Icon: CircleDashed },
  assumption: { tone: "violet", label: "AI / rule assumption", Icon: Sparkles },
  needs_confirmation: { tone: "orange", label: "Needs confirmation", Icon: CircleHelp },
};

export function FactStatusBadge({ status }: { status: string }) {
  const m = FACT_META[status] ?? { tone: "slate" as BadgeTone, label: humanize(status), Icon: CircleHelp };
  return (
    <Badge tone={m.tone}>
      <m.Icon className="h-3 w-3" aria-hidden />
      {m.label}
    </Badge>
  );
}

export function ApprovalBadge({ status }: { status: string }) {
  const tone: BadgeTone = status === "approved" ? "emerald" : status === "pending" ? "amber" : status === "rejected" ? "rose" : "slate";
  return <Badge tone={tone}>{humanize(status)}</Badge>;
}

export function HealthBadge({ status }: { status: string }) {
  return (
    <Badge tone={HEALTH_TONE[status] ?? "slate"}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: HEALTH_COLOR[status] ?? "#64748b" }} aria-hidden />
      {humanize(status)}
    </Badge>
  );
}

export function MonitoringBadge({ status }: { status: string }) {
  return <Badge tone={status === "active" ? "blue" : "slate"}>{status === "active" ? "Monitoring" : "Paused"}</Badge>;
}

export function JobStatusBadge({ status }: { status: string }) {
  const map: Record<string, { tone: BadgeTone; Icon: typeof CheckCircle2; spin?: boolean }> = {
    success: { tone: "emerald", Icon: CheckCircle2 },
    partial: { tone: "amber", Icon: AlertTriangle },
    failed: { tone: "rose", Icon: XCircle },
    running: { tone: "blue", Icon: Loader2, spin: true },
    queued: { tone: "slate", Icon: Clock },
    error: { tone: "rose", Icon: XCircle },
    blocked_robots: { tone: "rose", Icon: MinusCircle },
    not_modified: { tone: "slate", Icon: CheckCircle2 },
    skipped: { tone: "slate", Icon: MinusCircle },
  };
  const m = map[status] ?? { tone: "slate" as BadgeTone, Icon: CircleHelp };
  return (
    <Badge tone={m.tone}>
      <m.Icon className={`h-3 w-3 ${m.spin ? "animate-spin" : ""}`} aria-hidden />
      {humanize(status)}
    </Badge>
  );
}

export function CompetitorStatusBadge({ status }: { status: string }) {
  const tone: BadgeTone = status === "confirmed" ? "emerald" : status === "rejected" ? "rose" : "amber";
  return <Badge tone={tone}>{humanize(status)}</Badge>;
}

export function InterpretationBadge({ method }: { method: string }) {
  const ai = method === "llm" || method.toLowerCase().includes("ai");
  return (
    <Badge tone={ai ? "violet" : "slate"} title={ai ? "Interpretation written with a local LLM. It is interpretation, not evidence." : "Interpretation produced by transparent rules."}>
      {ai ? <Sparkles className="h-3 w-3" aria-hidden /> : null}
      {ai ? "AI interpretation" : "Rule-based interpretation"}
    </Badge>
  );
}
