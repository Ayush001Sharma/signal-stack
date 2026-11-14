"use client";

import * as React from "react";
import { toast } from "sonner";
import { Check, ChevronDown, Eye, Sparkles, X, Calculator, Undo2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CategoryBadge, InterpretationBadge, PolarityBadge, PriorityBadge, VerificationBadge } from "@/components/shared/badges";
import { EvidenceLink } from "@/components/shared/links";
import { ErrorBanner, KeyValue, Meter } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { api, errorMessage, paths } from "@/lib/api";
import type { Signal, SignalDetail } from "@/lib/types";
import { cn, fmtDate, fmtDateTime, humanize } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

export function ScoreBreakdownView({ signal }: { signal: Signal }) {
  const b = signal.score_breakdown || {};
  const comps = b.components || {};
  const weights = b.weights || {};
  const reasons = b.reasons || {};
  const keys = Object.keys(weights).length ? Object.keys(weights) : Object.keys(comps);
  return (
    <div className="space-y-3 rounded-lg border bg-muted/30 p-3 text-xs">
      {b.formula ? (
        <p className="font-mono text-[11px] text-muted-foreground">
          <span className="font-sans font-medium text-foreground">Formula: </span>
          {b.formula}
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[460px]">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
              <th className="py-1 pr-2 font-medium">Component</th>
              <th className="py-1 pr-2 font-medium">Value</th>
              <th className="py-1 pr-2 font-medium">Weight</th>
              <th className="py-1 pr-2 font-medium">Points</th>
              <th className="py-1 font-medium">Why</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const v = comps[k] ?? 0;
              const w = weights[k] ?? 0;
              return (
                <tr key={k} className="border-t border-border/60 align-top">
                  <td className="py-1.5 pr-2 font-medium">{humanize(k)}</td>
                  <td className="py-1.5 pr-2 tabular-nums">{(v * 100).toFixed(0)}%</td>
                  <td className="py-1.5 pr-2 tabular-nums">×{w.toFixed(2)}</td>
                  <td className="py-1.5 pr-2 tabular-nums">{(100 * v * w).toFixed(1)}</td>
                  <td className="py-1.5 text-muted-foreground">{reasons[k] ?? "—"}</td>
                </tr>
              );
            })}
            <tr className="border-t border-border font-semibold">
              <td className="py-1.5 pr-2" colSpan={3}>
                Priority score
              </td>
              <td className="py-1.5 pr-2 tabular-nums">{signal.priority_score.toFixed(1)}</td>
              <td className="py-1.5 font-normal text-muted-foreground">
                {b.thresholds ? `High ≥ ${b.thresholds.high}, Medium ≥ ${b.thresholds.medium}` : null}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {b.rule_interpretation ? (
        <p className="text-muted-foreground">
          <span className="font-medium text-foreground">Rule-based interpretation (audit copy): </span>
          {b.rule_interpretation.why}
        </p>
      ) : null}
    </div>
  );
}

export function SignalDetailDialog({ companyId, signalId, open, onOpenChange }: { companyId: number; signalId: number; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { data, error, isLoading, mutate } = useApi<SignalDetail>(open ? paths.signal(companyId, signalId) : null);
  const s = data?.signal;
  const raw = data?.raw_evidence;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="leading-snug">{s?.title ?? "Signal detail"}</DialogTitle>
          <DialogDescription>Full stored evidence for this signal, exactly as collected.</DialogDescription>
        </DialogHeader>
        {error ? <ErrorBanner error={error} onRetry={() => mutate()} /> : null}
        {isLoading || !s ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap gap-1.5">
              <CategoryBadge category={s.category} />
              <PriorityBadge priority={s.priority} score={s.priority_score} />
              <PolarityBadge polarity={s.polarity} />
              <VerificationBadge status={s.verification_status} />
              <Badge tone="outline">{humanize(s.signal_type)}</Badge>
            </div>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <KeyValue label="Publisher">{s.publisher ?? "—"}</KeyValue>
              <KeyValue label="Event date">{fmtDate(s.event_date, "Unknown")}</KeyValue>
              <KeyValue label="Discovered">{fmtDateTime(s.discovered_at)}</KeyValue>
              <KeyValue label="Corroborations">{s.corroboration_count}</KeyValue>
            </dl>
            <ScoreBreakdownView signal={s} />
            {raw ? (
              <div className="space-y-2 rounded-lg border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Raw evidence</h4>
                  <EvidenceLink url={raw.url} companyId={companyId}>
                    Open original
                  </EvidenceLink>
                </div>
                <p className="font-medium">{raw.title}</p>
                <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                  <KeyValue label="Published">{fmtDateTime(raw.published_at, "Unknown")}</KeyValue>
                  <KeyValue label="Date source">{humanize(raw.date_source)}</KeyValue>
                  <KeyValue label="Item type">{humanize(raw.item_type)}</KeyValue>
                  <KeyValue label="Version">{raw.version}</KeyValue>
                </dl>
                {raw.snippet ? <blockquote className="border-l-2 border-primary/50 pl-3 text-muted-foreground">{raw.snippet}</blockquote> : null}
                {raw.content ? (
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-3 font-sans text-xs text-muted-foreground">{raw.content}</pre>
                ) : null}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No raw item is attached to this signal (e.g. derived from an uploaded document).</p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function SignalCard({
  signal,
  companyId,
  onChanged,
  compact = false,
}: {
  signal: Signal;
  companyId: number;
  onChanged?: (s: Signal) => void;
  compact?: boolean;
}) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState(false);
  const ai = signal.interpretation_method === "llm";

  const setStatus = async (status: "new" | "reviewed" | "dismissed") => {
    setBusy(status);
    try {
      const s = await api.updateSignal(companyId, signal.id, status);
      toast.success(status === "dismissed" ? "Signal dismissed" : status === "reviewed" ? "Marked as reviewed" : "Signal restored");
      onChanged?.(s);
    } catch (e) {
      toast.error("Could not update signal", { description: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className={cn("p-4 sm:p-5", signal.status === "dismissed" && "opacity-60")}>
      <div className="flex flex-wrap items-center gap-1.5">
        <PriorityBadge priority={signal.priority} score={signal.priority_score} />
        <CategoryBadge category={signal.category} />
        <PolarityBadge polarity={signal.polarity} />
        <VerificationBadge status={signal.verification_status} />
        {signal.competitor_name ? <Badge tone="violet">vs {signal.competitor_name}</Badge> : null}
        <Badge tone="outline">{humanize(signal.signal_type)}</Badge>
        {signal.status !== "new" ? <Badge tone={signal.status === "reviewed" ? "emerald" : "slate"}>{humanize(signal.status)}</Badge> : null}
      </div>

      <h3 className="mt-2.5 text-[15px] font-semibold leading-snug">{signal.title}</h3>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{signal.publisher ?? signal.source_name ?? "Unknown publisher"}</span>
        <span>Event: {fmtDate(signal.event_date, "date unknown")}</span>
        <span>Discovered: {fmtDate(signal.discovered_at)}</span>
        {signal.corroboration_count > 0 ? <span>{signal.corroboration_count} corroborating report(s)</span> : null}
      </div>

      {!compact && signal.what_happened && signal.what_happened !== signal.title ? <p className="mt-2 text-sm text-foreground/90">{signal.what_happened}</p> : null}

      {signal.evidence_snippet ? (
        <blockquote className="mt-3 border-l-2 border-primary/40 pl-3 text-sm text-muted-foreground">
          “{signal.evidence_snippet}”{" "}
          <EvidenceLink url={signal.evidence_url} companyId={companyId} className="text-xs">
            {signal.evidence_url?.startsWith("internal://") ? "View uploaded document" : "Source"}
          </EvidenceLink>
        </blockquote>
      ) : signal.evidence_url ? (
        <div className="mt-2 text-xs">
          <EvidenceLink url={signal.evidence_url} companyId={companyId} />
        </div>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Meter label="Source reliability" value={signal.source_reliability} color="bg-sky-500" hint="How trustworthy the publisher/source is" />
        <Meter label="Evidence strength" value={signal.evidence_strength} color="bg-emerald-500" hint="How directly the evidence supports the claim" />
        <Meter label="Strategic relevance" value={signal.relevance} color="bg-violet-500" hint="How relevant this is to your business profile" />
      </div>

      {!compact && (signal.why_it_matters || signal.recommended_action) ? (
        <div className="mt-4 rounded-lg border border-dashed bg-muted/20 p-3 text-sm">
          <div className="mb-1.5 flex items-center gap-2">
            <InterpretationBadge method={signal.interpretation_method} />
            <span className="text-[11px] text-muted-foreground">
              {ai ? "Interpretation by local LLM — verify against evidence." : "Interpretation from transparent rules."}
              {ai && signal.ai_confidence != null ? ` Confidence ${Math.round(signal.ai_confidence * 100)}%.` : ""}
            </span>
          </div>
          {signal.why_it_matters ? (
            <p>
              <span className="font-medium">Why it matters: </span>
              <span className="text-foreground/85">{signal.why_it_matters}</span>
            </p>
          ) : null}
          {signal.recommended_action ? (
            <p className="mt-1">
              <span className="font-medium">Recommended action: </span>
              <span className="text-foreground/85">{signal.recommended_action}</span>
            </p>
          ) : null}
        </div>
      ) : null}

      <Collapsible className="mt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="group -ml-2 text-muted-foreground">
              <Calculator /> Why this score ({Math.round(signal.priority_score)}/100)
              <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" />
            </Button>
          </CollapsibleTrigger>
          <div className="flex flex-wrap gap-1.5">
            <Button variant="ghost" size="sm" onClick={() => setDetail(true)}>
              <Eye /> Raw evidence
            </Button>
            {signal.status === "new" ? (
              <>
                <Button variant="outline" size="sm" loading={busy === "reviewed"} onClick={() => setStatus("reviewed")}>
                  <Check /> Mark reviewed
                </Button>
                <Button variant="ghost" size="sm" loading={busy === "dismissed"} onClick={() => setStatus("dismissed")}>
                  <X /> Dismiss
                </Button>
              </>
            ) : (
              <Button variant="ghost" size="sm" loading={busy === "new"} onClick={() => setStatus("new")}>
                <Undo2 /> Restore
              </Button>
            )}
          </div>
        </div>
        <CollapsibleContent className="mt-2">
          <ScoreBreakdownView signal={signal} />
        </CollapsibleContent>
      </Collapsible>
      {detail ? <SignalDetailDialog companyId={companyId} signalId={signal.id} open={detail} onOpenChange={setDetail} /> : null}
    </Card>
  );
}

export function SignalMini({ signal, companyId }: { signal: Signal; companyId: number }) {
  return (
    <div className="flex items-start gap-3 py-2.5">
      <div className="mt-0.5 w-9 shrink-0 text-center">
        <div
          className={cn(
            "rounded-md py-1 text-xs font-semibold tabular-nums",
            signal.priority === "high" ? "bg-rose-500/15 text-rose-500" : signal.priority === "medium" ? "bg-amber-500/15 text-amber-500" : "bg-slate-500/15 text-slate-400",
          )}
          title={`Priority score ${signal.priority_score.toFixed(1)}`}
        >
          {Math.round(signal.priority_score)}
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm font-medium leading-snug">{signal.title}</p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          <CategoryBadge category={signal.category} />
          <PolarityBadge polarity={signal.polarity} />
          <span>{signal.publisher ?? signal.source_name}</span>
          <span>· {fmtDate(signal.event_date ?? signal.discovered_at)}</span>
          {signal.evidence_url ? <EvidenceLink url={signal.evidence_url} companyId={companyId} className="text-[11px]">evidence</EvidenceLink> : null}
        </div>
      </div>
      {signal.interpretation_method === "llm" ? <Sparkles className="mt-1 h-3.5 w-3.5 shrink-0 text-violet-400" aria-label="AI interpretation" /> : null}
    </div>
  );
}
