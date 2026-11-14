"use client";

import * as React from "react";
import { toast } from "sonner";
import { Download, FileCode2, FileDown, Printer, Sparkles, ExternalLink, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PolarityBadge, PriorityBadge, verificationToneFromLabel } from "@/components/shared/badges";
import { EvidenceLink } from "@/components/shared/links";
import { ErrorBanner } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { api, apiUrl, download, errorMessage, paths } from "@/lib/api";
import type { Brief, BriefAction, BriefItem } from "@/lib/types";
import { cn, fmtDate, fmtDateTime, humanize, pct } from "@/lib/utils";

function Ref({ r }: { r: string | null | undefined }) {
  if (!r) return null;
  return (
    <a href={`#ref-${r}`} className="rounded bg-primary/10 px-1 font-mono text-[11px] text-primary hover:underline" aria-label={`Source ${r} in appendix`}>
      [{r}]
    </a>
  );
}

function Empty({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return <p className="rounded-md border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground">{text}</p>;
}

function Item({ i, companyId, showAction = true, nextStep = false }: { i: BriefItem; companyId: number; showAction?: boolean; nextStep?: boolean }) {
  return (
    <article className="print-card rounded-lg border bg-background/30 p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h4 className="text-sm font-semibold leading-snug">
          {i.title} <Ref r={i.ref} />
        </h4>
        <div className="flex shrink-0 flex-wrap gap-1">
          <PriorityBadge priority={i.priority} score={i.priority_score} />
          <PolarityBadge polarity={i.polarity} />
        </div>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {i.competitor ? <span>Competitor: {i.competitor}</span> : null}
        <span>{i.publisher ?? "source"}</span>
        <span>published {i.when ? fmtDate(i.when) : "date unknown"}</span>
        <Badge tone={verificationToneFromLabel(i.verification)} className="text-[10px]">
          {i.verification}
        </Badge>
      </div>
      {i.evidence ? (
        <blockquote className="mt-2 border-l-2 border-primary/40 pl-3 text-sm text-muted-foreground">
          “{i.evidence}” <EvidenceLink url={i.evidence_url} companyId={companyId} className="text-xs">source</EvidenceLink>
        </blockquote>
      ) : null}
      <dl className="mt-2 space-y-1 text-sm">
        {i.why_it_matters ? (
          <div>
            <dt className="inline font-medium">Why it matters </dt>
            <dd className="inline text-foreground/85">
              <span className="text-[11px] text-violet-400">({i.interpretation.toLowerCase()})</span>: {i.why_it_matters}
            </dd>
          </div>
        ) : null}
        <div className="text-xs text-muted-foreground">
          <dt className="inline font-medium text-foreground">Impact: </dt>
          <dd className="inline">
            {humanize(i.polarity)} · {humanize(i.business_area)} · impact {pct(i.impact)}, urgency {pct(i.urgency)}, relevance {pct(i.relevance)}
          </dd>
        </div>
        {showAction && (nextStep ? i.next_step : i.recommended_action) ? (
          <div>
            <dt className="inline font-medium">{nextStep ? "Next step: " : "Recommended action: "}</dt>
            <dd className="inline text-foreground/85">{nextStep ? i.next_step : i.recommended_action}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}

function Section({ n, title, children, id }: { n: number; title: string; children: React.ReactNode; id: string }) {
  return (
    <section aria-labelledby={id} className="scroll-mt-20">
      <Card className="print-card">
        <CardHeader>
          <CardTitle id={id} className="flex items-center gap-2 text-base">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/15 text-xs font-semibold text-primary">{n}</span>
            {title}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">{children}</CardContent>
      </Card>
    </section>
  );
}

function ActionsTracker({ brief, companyId }: { brief: Brief; companyId: number }) {
  const { data, error, mutate } = useApi<BriefAction[]>(paths.briefActions(companyId, brief.id));
  const [owners, setOwners] = React.useState<Record<number, string>>({});

  const update = async (a: BriefAction, body: { status?: string; owner?: string | null }) => {
    try {
      await api.updateAction(companyId, a.id, body);
      toast.success(body.status ? `Action marked ${humanize(body.status).toLowerCase()}` : "Owner updated");
      await mutate();
    } catch (e) {
      toast.error("Could not update action", { description: errorMessage(e) });
    }
  };

  if (error) return <ErrorBanner error={error} onRetry={() => mutate()} />;
  const actions = data ?? [];
  if (!data) {
    // Fall back to the brief content while tracking loads.
    return null;
  }
  if (!actions.length) return <Empty text="No actions recommended — no evidence-backed developments required a response." />;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8">#</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Reason</TableHead>
          <TableHead>Priority</TableHead>
          <TableHead className="w-44">Owner</TableHead>
          <TableHead className="w-40">Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {actions.map((a, n) => {
          const refMatch = a.reason?.match(/^\[(S\d+)\]\s*(.*)$/);
          return (
            <TableRow key={a.id} className={cn(a.status === "done" && "opacity-70", a.status === "dismissed" && "opacity-50")}>
              <TableCell className="tabular-nums text-muted-foreground">{n + 1}</TableCell>
              <TableCell className={cn("min-w-[220px] font-medium", a.status === "done" && "line-through")}>{a.action}</TableCell>
              <TableCell className="min-w-[200px] text-xs text-muted-foreground">
                {refMatch ? (
                  <>
                    <Ref r={refMatch[1]} /> {refMatch[2]}
                  </>
                ) : (
                  a.reason
                )}
              </TableCell>
              <TableCell>
                <PriorityBadge priority={a.priority} />
              </TableCell>
              <TableCell>
                <Input
                  aria-label={`Owner for action ${n + 1}`}
                  className="h-8 text-xs"
                  value={owners[a.id] ?? a.owner ?? ""}
                  maxLength={100}
                  onChange={(e) => setOwners((o) => ({ ...o, [a.id]: e.target.value }))}
                  onBlur={() => {
                    const v = owners[a.id];
                    if (v !== undefined && v !== (a.owner ?? "")) void update(a, { owner: v || null });
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  }}
                />
              </TableCell>
              <TableCell>
                <Select value={a.status} onValueChange={(v) => update(a, { status: v })}>
                  <SelectTrigger className="h-8 text-xs" aria-label={`Status for action ${n + 1}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="in_progress">In progress</SelectItem>
                    <SelectItem value="done">Done</SelectItem>
                    <SelectItem value="dismissed">Dismissed</SelectItem>
                  </SelectContent>
                </Select>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

const TOC = [
  "Executive Summary",
  "Customer Signals",
  "Competitor Intelligence",
  "Market Intelligence",
  "Internal Business Intelligence",
  "Opportunities Identified",
  "Risks & Threats",
  "Recommended Actions for This Week",
  "What We Should Watch",
  "Source Appendix",
];

export function BriefExportButtons({ brief, companyId }: { brief: Brief; companyId: number }) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const base = `brief-${companyId}-${brief.id}-${brief.period_end.slice(0, 10)}`;
  const doDownload = async (kind: "md" | "pdf") => {
    setBusy(kind);
    try {
      await download(kind === "md" ? paths.briefMarkdown(companyId, brief.id) : paths.briefPdf(companyId, brief.id), `${base}.${kind}`);
      toast.success(kind === "md" ? "Markdown downloaded" : "PDF downloaded");
    } catch (e) {
      toast.error("Export failed", { description: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <Button variant="outline" size="sm" loading={busy === "md"} onClick={() => doDownload("md")}>
        <FileDown /> Markdown
      </Button>
      <Button variant="outline" size="sm" loading={busy === "pdf"} onClick={() => doDownload("pdf")}>
        <Download /> PDF
      </Button>
      <Button variant="outline" size="sm" asChild>
        <a href={apiUrl(paths.briefHtml(companyId, brief.id))} target="_blank" rel="noopener noreferrer">
          <FileCode2 /> Email-ready HTML <ExternalLink className="h-3 w-3" />
          <span className="sr-only">(opens in new tab)</span>
        </a>
      </Button>
      <Button variant="outline" size="sm" onClick={() => window.print()}>
        <Printer /> Print
      </Button>
    </>
  );
}

export function BriefView({ brief, companyId }: { brief: Brief; companyId: number }) {
  const c = brief.content;
  const s = brief.stats;
  return (
    <div className="space-y-5">
      {/* Masthead */}
      <Card className="glow-card print-card overflow-hidden">
        <div className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge tone="default">Monday Morning Intelligence Brief</Badge>
            <span>
              {fmtDate(c.period.start)} → {fmtDate(c.period.end)}
            </span>
            <span>· generated {fmtDateTime(c.generated_at)}</span>
            <span>· trigger: {humanize(brief.trigger)}</span>
          </div>
          <h1 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">{brief.title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {c.company.name} · {c.company.industry ?? "industry n/a"} ·{" "}
            <EvidenceLink url={c.company.website} companyId={companyId} className="text-sm" />
          </p>
          <div className="mt-4 rounded-lg border-l-4 border-primary bg-primary/5 p-4">
            <p className="whitespace-pre-line text-[15px] leading-relaxed">{c.narrative.text}</p>
            <p className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Sparkles className="h-3 w-3" aria-hidden /> Summary method: {c.narrative.method}
            </p>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
            {[
              ["Meaningful signals", s.meaningful_signals],
              ["High priority", s.high_priority],
              ["Opportunities", s.opportunities],
              ["Risks", s.risks],
              ["Internal signals", s.internal_signals],
              ["Approved sources", s.approved_sources],
            ].map(([l, v]) => (
              <div key={l as string} className="rounded-md border bg-background/40 p-2.5">
                <p className="text-[11px] text-muted-foreground">{l}</p>
                <p className="text-lg font-semibold tabular-nums">{(v as number | undefined) ?? 0}</p>
              </div>
            ))}
          </div>
          {s.last_crawl ? (
            <p className="mt-3 text-[11px] text-muted-foreground">
              Last crawl {fmtDateTime(s.last_crawl.started)} — {s.last_crawl.status}
              {s.last_crawl.message ? `: ${s.last_crawl.message}` : ""}
            </p>
          ) : null}
        </div>
      </Card>

      <nav aria-label="Brief sections" className="no-print">
        <ol className="flex flex-wrap gap-1.5 text-xs">
          {TOC.map((t, n) => (
            <li key={t}>
              <a href={`#sec-${n + 1}`} className="inline-block rounded-md border px-2 py-1 text-muted-foreground hover:border-primary/40 hover:text-foreground">
                {n + 1}. {t}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <Section n={1} title="Executive Summary" id="sec-1">
        {c.executive_summary.length ? c.executive_summary.map((i) => <Item key={i.ref + i.signal_id} i={i} companyId={companyId} />) : <Empty text="No meaningful developments were detected in this period." />}
      </Section>

      <Section n={2} title="Customer Signals" id="sec-2">
        <Empty text={c.customer_signals.empty_message} />
        {!c.customer_signals.empty_message ? (
          <>
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">Themes:</span>
              {c.customer_signals.themes.map((t) => (
                <Badge key={t.type} tone="blue">
                  {humanize(t.type)} ({t.count})
                </Badge>
              ))}
              {c.customer_signals.average_sentiment != null ? (
                <span className="text-muted-foreground">· average sentiment {c.customer_signals.average_sentiment > 0 ? "+" : ""}{c.customer_signals.average_sentiment.toFixed(2)}</span>
              ) : null}
            </div>
            {c.customer_signals.items.map((i) => (
              <Item key={i.ref + i.signal_id} i={i} companyId={companyId} />
            ))}
          </>
        ) : null}
      </Section>

      <Section n={3} title="Competitor Intelligence" id="sec-3">
        <Empty text={c.competitor_intelligence.empty_message} />
        {c.competitor_intelligence.groups.map((g) => (
          <div key={g.competitor} className="space-y-2">
            <h3 className="text-sm font-semibold text-violet-400">{g.competitor}</h3>
            {g.items.map((i) => (
              <Item key={i.ref + i.signal_id} i={i} companyId={companyId} />
            ))}
          </div>
        ))}
      </Section>

      <Section n={4} title="Market Intelligence" id="sec-4">
        <Empty text={c.market_intelligence.empty_message} />
        {!c.market_intelligence.empty_message ? (
          <>
            <h3 className="text-sm font-semibold">Material to the business</h3>
            {c.market_intelligence.material.length ? c.market_intelligence.material.map((i) => <Item key={i.ref + i.signal_id} i={i} companyId={companyId} />) : <p className="text-sm text-muted-foreground">None this period.</p>}
            <h3 className="pt-2 text-sm font-semibold">General industry context (lower materiality)</h3>
            {c.market_intelligence.general.length ? c.market_intelligence.general.map((i) => <Item key={i.ref + i.signal_id} i={i} companyId={companyId} showAction={false} />) : <p className="text-sm text-muted-foreground">None.</p>}
          </>
        ) : null}
      </Section>

      <Section n={5} title="Internal Business Intelligence" id="sec-5">
        <Empty text={c.internal_intelligence.empty_message} />
        {c.internal_intelligence.synthetic_note ? (
          <div role="note" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200 print:text-black">
            <strong>SYNTHETIC TEST DATA.</strong> {c.internal_intelligence.synthetic_note}
          </div>
        ) : null}
        {c.internal_intelligence.documents.length ? (
          <div className="text-xs text-muted-foreground">
            Documents analysed:{" "}
            {c.internal_intelligence.documents.map((d, n) => (
              <span key={d.id}>
                {n > 0 ? "; " : ""}
                {d.synthetic ? <span className="mr-1 rounded bg-amber-500/20 px-1 text-amber-800 dark:text-amber-300">SYNTHETIC</span> : null}<span className="text-foreground">{d.filename}</span> ({d.records} records, uploaded {fmtDate(d.uploaded)}){d.description ? ` — ${d.description}` : ""}
              </span>
            ))}
          </div>
        ) : null}
        {c.internal_intelligence.items.map((i) => (
          <Item key={i.ref + i.signal_id} i={i} companyId={companyId} />
        ))}
      </Section>

      <Section n={6} title="Opportunities Identified" id="sec-6">
        {c.opportunities.map((i) => (
          <Item key={i.ref + i.signal_id} i={i} companyId={companyId} nextStep />
        ))}
        {c.opportunities_note ? (
          <p className="flex items-start gap-1.5 text-sm italic text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> {c.opportunities_note}
          </p>
        ) : null}
      </Section>

      <Section n={7} title="Risks & Threats" id="sec-7">
        {c.risks.map((i) => (
          <Item key={i.ref + i.signal_id} i={i} companyId={companyId} />
        ))}
        <Empty text={c.risks_note} />
      </Section>

      <Section n={8} title="Recommended Actions for This Week" id="sec-8">
        <p className="no-print text-xs text-muted-foreground">Track progress: assign an owner and update the status. Changes are saved immediately.</p>
        <ActionsTracker brief={brief} companyId={companyId} />
        {/* Print fallback: static list from the brief content */}
        <ol className="hidden list-decimal space-y-1 pl-5 text-sm print:block">
          {c.recommended_actions.map((a, n) => (
            <li key={n}>
              <strong>{a.action}</strong> — {a.reason} · owner: {a.owner} · priority {a.priority}
            </li>
          ))}
        </ol>
      </Section>

      <Section n={9} title="What We Should Watch" id="sec-9">
        {c.watch_list.length ? (
          <ul className="space-y-2">
            {c.watch_list.map((w, n) => (
              <li key={n} className="rounded-lg border p-3 text-sm">
                <p className="font-medium">
                  {w.title} <Ref r={w.ref} />
                </p>
                <p className="mt-0.5 text-muted-foreground">{w.why}</p>
                {w.url ? <EvidenceLink url={w.url} companyId={companyId} className="mt-1 text-xs" /> : null}
              </li>
            ))}
          </ul>
        ) : (
          <Empty text="Nothing flagged for watching this period." />
        )}
      </Section>

      <Section n={10} title="Source Appendix" id="sec-10">
        {c.source_appendix.length ? (
          <Table className="text-xs">
            <TableHeader>
              <TableRow>
                <TableHead>Ref</TableHead>
                <TableHead>Development</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Published</TableHead>
                <TableHead>Discovered</TableHead>
                <TableHead className="min-w-[220px]">Snippet</TableHead>
                <TableHead>Verification</TableHead>
                <TableHead className="text-right">Reliability</TableHead>
                <TableHead className="text-right">Evidence</TableHead>
                <TableHead className="text-right">Relevance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {c.source_appendix.map((a) => (
                <TableRow key={a.ref} id={`ref-${a.ref}`} className="scroll-mt-24 target:bg-primary/10">
                  <TableCell className="font-mono font-medium text-primary">{a.ref}</TableCell>
                  <TableCell className="min-w-[200px]">
                    {a.url ? (
                      <EvidenceLink url={a.url} companyId={companyId}>
                        {a.title}
                      </EvidenceLink>
                    ) : (
                      a.title
                    )}
                  </TableCell>
                  <TableCell>{a.source ?? "—"}</TableCell>
                  <TableCell className="whitespace-nowrap">{a.published === "unknown" ? "unknown" : fmtDate(a.published)}</TableCell>
                  <TableCell className="whitespace-nowrap">{fmtDate(a.discovered)}</TableCell>
                  <TableCell className="text-muted-foreground">{a.snippet ? `“${a.snippet.slice(0, 300)}${a.snippet.length > 300 ? "…" : ""}”` : "—"}</TableCell>
                  <TableCell>
                    <Badge tone={verificationToneFromLabel(a.verification)} className="whitespace-normal">
                      {a.verification}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{pct(a.source_reliability)}</TableCell>
                  <TableCell className="text-right tabular-nums">{pct(a.evidence_strength)}</TableCell>
                  <TableCell className="text-right tabular-nums">{pct(a.strategic_relevance)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Empty text="No sources were cited in this brief." />
        )}
      </Section>

      <Card className="print-card">
        <CardContent className="space-y-1.5 p-5 text-xs text-muted-foreground">
          <p className="text-sm font-semibold text-foreground">Methodology</p>
          <p>
            <span className="font-medium text-foreground">Ranking: </span>
            {c.methodology.ranking}
          </p>
          <p>
            <span className="font-medium text-foreground">Evidence policy: </span>
            {c.methodology.evidence_policy}
          </p>
          <p>
            <span className="font-medium text-foreground">Window: </span>
            {c.methodology.window}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
