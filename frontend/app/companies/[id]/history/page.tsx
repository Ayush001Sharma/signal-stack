"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, ClipboardCheck, FileText, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorBanner, PageHeader, Pagination } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, paths } from "@/lib/api";
import type { Audit, BriefSummary, Page } from "@/lib/types";
import { fmtDate, fmtDateTime, humanize } from "@/lib/utils";

export default function HistoryPage() {
  const id = useCompanyId();
  const jobs = useJobRunner(id);
  const [page, setPage] = React.useState(1);
  const briefs = useApi<Page<BriefSummary>>(paths.briefs(id, { page, page_size: 10 }), { keepPreviousData: true });
  const audits = useApi<Audit[]>(paths.audits(id));

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Historical reports" title="Reports history" description="Every Monday Brief and monthly Signal Stack audit, kept for reference and comparison." />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" aria-hidden /> Monday Briefs
          </CardTitle>
          <CardDescription>{briefs.data ? `${briefs.data.total} brief${briefs.data.total === 1 ? "" : "s"}` : "Loading…"}</CardDescription>
        </CardHeader>
        <CardContent>
          {briefs.error ? <ErrorBanner error={briefs.error} onRetry={() => briefs.mutate()} /> : null}
          {!briefs.data ? (
            <Skeleton className="h-32 w-full" />
          ) : briefs.data.items.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No briefs yet"
              description="Briefs are generated every week on schedule, or on demand."
              action={
                <Button loading={jobs.isRunning("brief")} onClick={() => jobs.run("brief", "Monday Brief", () => api.generateBrief(id, {}))}>
                  <Sparkles /> Generate brief now
                </Button>
              }
            />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Brief</TableHead>
                    <TableHead>Period</TableHead>
                    <TableHead>Trigger</TableHead>
                    <TableHead className="text-right">Signals</TableHead>
                    <TableHead className="text-right">High</TableHead>
                    <TableHead className="text-right">Opp.</TableHead>
                    <TableHead className="text-right">Risks</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {briefs.data.items.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell className="min-w-[260px]">
                        <Link href={`/companies/${id}/briefs/${b.id}`} className="font-medium hover:text-primary hover:underline">
                          {b.title}
                        </Link>
                        <p className="text-[11px] text-muted-foreground">Generated {fmtDateTime(b.generated_at)}</p>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs">
                        {fmtDate(b.period_start)} → {fmtDate(b.period_end)}
                      </TableCell>
                      <TableCell>
                        <Badge tone={b.trigger === "scheduled" ? "blue" : "slate"}>{humanize(b.trigger)}</Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{b.stats.meaningful_signals ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums text-rose-400">{b.stats.high_priority ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums text-emerald-400">{b.stats.opportunities ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums text-rose-400">{b.stats.risks ?? 0}</TableCell>
                      <TableCell>
                        <Button variant="ghost" size="icon-sm" asChild>
                          <Link href={`/companies/${id}/briefs/${b.id}`} aria-label={`Open brief ${b.id}`}>
                            <ArrowRight />
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Pagination page={briefs.data.page} pageSize={briefs.data.page_size} total={briefs.data.total} onPage={setPage} />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ClipboardCheck className="h-4 w-4 text-primary" aria-hidden /> Monthly Signal Stack audits
          </CardTitle>
          <CardDescription>Source availability, duplicates, inactivity and relevance decline, with recommendations.</CardDescription>
        </CardHeader>
        <CardContent>
          {audits.error ? <ErrorBanner error={audits.error} onRetry={() => audits.mutate()} /> : null}
          {!audits.data ? (
            <Skeleton className="h-24 w-full" />
          ) : audits.data.length === 0 ? (
            <EmptyState
              icon={ShieldCheck}
              title="No audits yet"
              description="Audits run monthly on schedule, or on demand from Health & Audit."
              action={
                <Button loading={jobs.isRunning("audit")} onClick={() => jobs.run("audit", "Signal Stack audit", () => api.runAudit(id))}>
                  <ShieldCheck /> Run audit now
                </Button>
              }
            />
          ) : (
            <ul className="divide-y">
              {audits.data.map((a) => {
                const s = a.content.summary ?? {};
                return (
                  <li key={a.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <Link href={`/companies/${id}/audits/${a.id}`} className="font-medium hover:text-primary hover:underline">
                        Audit #{a.id} · {fmtDate(a.generated_at)}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {s.approved_sources ?? 0} sources · {s.dead_or_unavailable ?? 0} unavailable · {s.duplicates ?? 0} duplicates · {s.inactive ?? 0} inactive · {s.recommended_additions ?? 0} additions ·{" "}
                        {s.recommended_removals ?? 0} removals recommended
                      </p>
                    </div>
                    <Button variant="outline" size="sm" asChild>
                      <Link href={`/companies/${id}/audits/${a.id}`}>
                        View report <ArrowRight />
                      </Link>
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
