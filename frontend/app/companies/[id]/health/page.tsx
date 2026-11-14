"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { AlertTriangle, Pause, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { AuditView } from "@/components/audit-view";
import { HealthDonut } from "@/components/charts";
import { HEALTH_COLOR, HealthBadge, JobStatusBadge } from "@/components/shared/badges";
import { EvidenceLink } from "@/components/shared/links";
import { EmptyState, ErrorBanner, PageHeader, Pagination } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, errorMessage, paths } from "@/lib/api";
import type { Audit, CrawlLog, Page, Source } from "@/lib/types";
import { fmtDateTime, fmtRelative, humanize } from "@/lib/utils";

const STATES = ["healthy", "degraded", "failing", "dead", "blocked", "unknown"];
const HELP: Record<string, string> = {
  healthy: "Last check succeeded",
  degraded: "Recent errors, still partially working",
  failing: "3+ consecutive failures",
  dead: "404/410 — the URL no longer exists",
  blocked: "robots.txt disallows access",
  unknown: "Not checked yet",
};

export default function HealthPage() {
  const id = useCompanyId();
  const jobs = useJobRunner(id);
  const [logPage, setLogPage] = React.useState(1);
  const sources = useApi<Source[]>(paths.sources(id, { approval_status: "approved" }));
  const logs = useApi<Page<CrawlLog>>(paths.crawlLogs(id, { status: "error", page: logPage, page_size: 10 }), { keepPreviousData: true });
  const audits = useApi<Audit[]>(paths.audits(id));
  const latest = audits.data?.[0];

  const counts = React.useMemo(() => {
    const c: Record<string, number> = Object.fromEntries(STATES.map((s) => [s, 0]));
    for (const s of sources.data ?? []) c[s.health_status] = (c[s.health_status] ?? 0) + 1;
    return c;
  }, [sources.data]);
  const withErrors = (sources.data ?? []).filter((s) => s.last_error || s.consecutive_failures > 0).sort((a, b) => b.consecutive_failures - a.consecutive_failures);
  const nameById = new Map((sources.data ?? []).map((s) => [s.id, s.name]));

  const pause = async (s: Source) => {
    try {
      await api.updateSource(id, s.id, { monitoring_status: "paused" });
      toast.success(`Paused ${s.name}`);
      await sources.mutate();
    } catch (e) {
      toast.error("Could not pause", { description: errorMessage(e) });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Source health & audit"
        title="Health & audit"
        description="Keep the Signal Stack trustworthy: spot failing sources, review errors and act on the monthly audit."
        actions={
          <Button loading={jobs.isRunning("audit")} onClick={() => jobs.run("audit", "Signal Stack audit", () => api.runAudit(id))}>
            <ShieldCheck /> Run audit now
          </Button>
        }
      />
      {sources.error ? <ErrorBanner error={sources.error} onRetry={() => sources.mutate()} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader>
            <CardTitle>Approved source health</CardTitle>
            <CardDescription>{sources.data ? `${sources.data.length} approved sources` : "Loading…"}</CardDescription>
          </CardHeader>
          <CardContent>
            {!sources.data ? <Skeleton className="h-44 w-full" /> : sources.data.length ? <HealthDonut health={counts} /> : <p className="py-8 text-center text-sm text-muted-foreground">No approved sources.</p>}
          </CardContent>
        </Card>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {STATES.map((s) => (
            <Link key={s} href={`/companies/${id}/sources?health=${s}`} className="rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <Card className="h-full p-4 transition-colors hover:border-primary/40">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: HEALTH_COLOR[s] }} aria-hidden />
                  <span className="text-sm font-medium">{humanize(s)}</span>
                </div>
                <p className="mt-2 text-2xl font-semibold tabular-nums">{counts[s] ?? 0}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">{HELP[s]}</p>
              </Card>
            </Link>
          ))}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" aria-hidden /> Sources with errors
          </CardTitle>
          <CardDescription>Approved sources whose recent checks failed.</CardDescription>
        </CardHeader>
        <CardContent>
          {!sources.data ? (
            <Skeleton className="h-24 w-full" />
          ) : withErrors.length === 0 ? (
            <p className="text-sm text-muted-foreground">No source errors — every approved source is responding.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Health</TableHead>
                  <TableHead className="text-right">Failures</TableHead>
                  <TableHead>Last error</TableHead>
                  <TableHead>Last checked</TableHead>
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {withErrors.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="max-w-[240px]">
                      <p className="truncate font-medium">{s.name}</p>
                      <EvidenceLink url={s.url} companyId={id} className="text-[11px]" />
                    </TableCell>
                    <TableCell>
                      <HealthBadge status={s.health_status} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{s.consecutive_failures}</TableCell>
                    <TableCell className="max-w-[360px] text-xs text-rose-400">
                      <span className="line-clamp-2 break-words">{s.last_error ?? "—"}</span>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{fmtRelative(s.last_checked_at, "Never")}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button size="xs" variant="outline" loading={jobs.isRunning(`check-${s.id}`)} onClick={() => jobs.run(`check-${s.id}`, `Check ${s.name}`, () => api.checkSource(id, s.id))}>
                          <RefreshCw className="h-3 w-3" /> Check
                        </Button>
                        {s.monitoring_status === "active" ? (
                          <Button size="xs" variant="ghost" onClick={() => pause(s)}>
                            <Pause className="h-3 w-3" /> Pause
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent failed crawls</CardTitle>
          <CardDescription>Crawl log entries with status “error”.</CardDescription>
        </CardHeader>
        <CardContent>
          {logs.error ? <ErrorBanner error={logs.error} onRetry={() => logs.mutate()} /> : null}
          {!logs.data ? (
            <Skeleton className="h-24 w-full" />
          ) : logs.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No failed crawls recorded.</p>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">HTTP</TableHead>
                    <TableHead>Error</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.data.items.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell className="whitespace-nowrap text-xs">{fmtDateTime(l.started_at)}</TableCell>
                      <TableCell className="max-w-[220px] truncate">{nameById.get(l.source_id) ?? `Source #${l.source_id}`}</TableCell>
                      <TableCell>
                        <JobStatusBadge status={l.status} />
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{l.http_status ?? "—"}</TableCell>
                      <TableCell className="max-w-[420px] text-xs text-rose-400">
                        <span className="line-clamp-2 break-words">{l.error ?? "—"}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Pagination page={logs.data.page} pageSize={logs.data.page_size} total={logs.data.total} onPage={setLogPage} />
            </>
          )}
        </CardContent>
      </Card>

      <section aria-labelledby="audit-h" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="audit-h" className="text-sm font-semibold">
            Latest monthly audit
          </h2>
          {audits.data && audits.data.length > 1 ? (
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/companies/${id}/history`}>All audits</Link>
            </Button>
          ) : null}
        </div>
        {audits.error ? <ErrorBanner error={audits.error} onRetry={() => audits.mutate()} /> : null}
        {!audits.data ? (
          <Skeleton className="h-40 w-full" />
        ) : latest ? (
          <AuditView audit={latest} companyId={id} />
        ) : (
          <EmptyState
            icon={ShieldCheck}
            title="No audit has run yet"
            description="The audit checks every approved source for availability, duplicates, inactivity and declining relevance, then recommends additions and removals."
            action={
              <Button loading={jobs.isRunning("audit")} onClick={() => jobs.run("audit", "Signal Stack audit", () => api.runAudit(id))}>
                <ShieldCheck /> Run audit now
              </Button>
            }
          />
        )}
      </section>
    </div>
  );
}
