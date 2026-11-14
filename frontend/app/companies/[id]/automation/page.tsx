"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CalendarClock, ChevronDown, ClipboardCheck, FileText, Play, Radar, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { JobStatusBadge } from "@/components/shared/badges";
import { ErrorBanner, PageHeader, Pagination } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, paths } from "@/lib/api";
import type { CrawlRun, JobRun, Page, Schedule, SchedulerStatus } from "@/lib/types";
import { describeTrigger, fmtDateTime, fmtDuration, fmtRelative, humanize } from "@/lib/utils";

const DAY: Record<string, string> = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };
const JOB_TYPES = ["setup", "research", "competitors", "discovery", "crawl", "weekly_brief", "monthly_audit", "reassess_context"];

function JobRow({ j }: { j: JobRun }) {
  const [open, setOpen] = React.useState(false);
  const hasMore = !!j.error || Object.keys(j.details ?? {}).length > 0;
  return (
    <>
      <TableRow>
        <TableCell className="tabular-nums text-muted-foreground">#{j.id}</TableCell>
        <TableCell className="font-medium">{humanize(j.job_type)}</TableCell>
        <TableCell>
          <Badge tone={j.trigger === "scheduled" ? "blue" : "slate"}>{humanize(j.trigger)}</Badge>
        </TableCell>
        <TableCell>
          <JobStatusBadge status={j.status} />
        </TableCell>
        <TableCell className="whitespace-nowrap text-xs">{fmtDateTime(j.started_at)}</TableCell>
        <TableCell className="whitespace-nowrap text-xs tabular-nums">{j.finished_at ? fmtDuration(j.started_at, j.finished_at) : j.status === "running" ? "running…" : "—"}</TableCell>
        <TableCell className="max-w-[360px] text-xs text-muted-foreground">
          <span className="line-clamp-2">{j.message ?? "—"}</span>
        </TableCell>
        <TableCell>
          {hasMore ? (
            <Button variant="ghost" size="icon-sm" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={`${open ? "Hide" : "Show"} details for job ${j.id}`}>
              <ChevronDown className={open ? "rotate-180 transition-transform" : "transition-transform"} />
            </Button>
          ) : null}
        </TableCell>
      </TableRow>
      {open ? (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={8} className="bg-muted/20">
            {j.error ? (
              <div className="mb-2">
                <p className="mb-1 text-xs font-medium text-rose-500">Error</p>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-background/60 p-3 font-mono text-[11px] text-rose-300">{j.error}</pre>
              </div>
            ) : null}
            <p className="mb-1 text-xs font-medium">Details</p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-background/60 p-3 font-mono text-[11px] text-muted-foreground">{JSON.stringify(j.details, null, 2)}</pre>
          </TableCell>
        </TableRow>
      ) : null}
    </>
  );
}

function AutomationInner() {
  const id = useCompanyId();
  const search = useSearchParams();
  const jobs = useJobRunner(id);
  const [status, setStatus] = React.useState(search.get("status") ?? "all");
  const [type, setType] = React.useState("all");
  const [page, setPage] = React.useState(1);
  const [crawlPage, setCrawlPage] = React.useState(1);
  React.useEffect(() => setPage(1), [status, type]);

  const sched = useApi<SchedulerStatus>(paths.scheduler(), { refreshInterval: 60000 });
  const cfg = useApi<Schedule>(paths.schedule(id));
  const history = useApi<Page<JobRun>>(paths.jobs({ company_id: id, status: status === "all" ? undefined : status, job_type: type === "all" ? undefined : type, page, page_size: 15 }), {
    refreshInterval: (d) => (d?.items.some((j) => j.status === "running" || j.status === "queued") ? 4000 : 30000),
    keepPreviousData: true,
  });
  const crawls = useApi<Page<CrawlRun>>(paths.crawlRuns(id, { page: crawlPage, page_size: 10 }), { keepPreviousData: true });

  const jobFor = (t: string) => sched.data?.jobs.find((j) => j.company_id === id && j.job_type === t);
  const s = cfg.data;
  const processes = [
    {
      key: "weekly_brief",
      title: "Weekly Intelligence Brief",
      icon: FileText,
      enabled: s?.weekly_enabled,
      cron: s ? `Every ${DAY[s.weekly_day_of_week] ?? s.weekly_day_of_week} at ${s.weekly_time} (${s.timezone}) · ${s.brief_lookback_days}-day lookback` : "",
      desc: "Crawls approved sources, scores new signals and generates the Monday Morning Brief.",
      run: () => jobs.run("brief", "Monday Brief", () => api.generateBrief(id, {})),
      runKey: "brief",
    },
    {
      key: "monthly_audit",
      title: "Monthly Signal Stack Audit",
      icon: ClipboardCheck,
      enabled: s?.monthly_enabled,
      cron: s ? `Monthly on day ${s.monthly_day} at ${s.monthly_time} (${s.timezone})` : "",
      desc: "Checks every source for availability, duplicates, inactivity and declining relevance; proposes changes.",
      run: () => jobs.run("audit", "Signal Stack audit", () => api.runAudit(id)),
      runKey: "audit",
    },
    {
      key: "crawl",
      title: "Source monitoring crawl",
      icon: Radar,
      enabled: s?.crawl_enabled,
      cron: s ? `Every ${s.crawl_interval_hours} hour${s.crawl_interval_hours === 1 ? "" : "s"}` : "",
      desc: "Polls approved, active sources politely (robots.txt, per-host delay) and creates scored signals.",
      run: () => jobs.run("crawl", "Crawl", () => api.crawlNow(id)),
      runKey: "crawl",
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Automation & scheduler"
        title="Automation"
        description="Two independent scheduled processes — the weekly brief and the monthly audit — plus continuous source monitoring."
        actions={
          <Button variant="outline" asChild>
            <Link href={`/companies/${id}/settings`}>
              <Settings /> Edit schedule
            </Link>
          </Button>
        }
      />
      {sched.error ? <ErrorBanner error={sched.error} onRetry={() => sched.mutate()} /> : null}
      {sched.data && !sched.data.running ? (
        <div role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
          The scheduler is not running on the backend — scheduled jobs will not fire until it is enabled. Manual runs still work.
        </div>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-3">
        {processes.map((p) => {
          const j = jobFor(p.key);
          return (
            <Card key={p.key} className="flex flex-col">
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="flex items-center gap-2">
                    <p.icon className="h-4 w-4 text-primary" aria-hidden /> {p.title}
                  </CardTitle>
                  {s ? <Badge tone={p.enabled ? "emerald" : "slate"}>{p.enabled ? "Enabled" : "Disabled"}</Badge> : <Skeleton className="h-5 w-16" />}
                </div>
                <CardDescription>{p.desc}</CardDescription>
              </CardHeader>
              <CardContent className="mt-auto space-y-3 text-sm">
                <div>
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Schedule</p>
                  <p>{p.cron || "—"}</p>
                  {j ? <p className="text-xs text-muted-foreground">Scheduler: {describeTrigger(j.trigger)}</p> : null}
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Next run (your local time)</p>
                  <p className="flex items-center gap-1.5">
                    <CalendarClock className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    {j?.next_run_time ? (
                      <>
                        {fmtDateTime(j.next_run_time)} <span className="text-xs text-muted-foreground">({fmtRelative(j.next_run_time)})</span>
                      </>
                    ) : p.enabled === false ? (
                      "Not scheduled (disabled)"
                    ) : (
                      "—"
                    )}
                  </p>
                </div>
                <Button className="w-full" variant="outline" loading={jobs.isRunning(p.runKey)} onClick={p.run}>
                  <Play /> Run now
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Execution history</CardTitle>
              <CardDescription>Every job run for this company, scheduled or manual.</CardDescription>
            </div>
            <div className="flex gap-2">
              <Select value={type} onValueChange={setType}>
                <SelectTrigger className="w-44" aria-label="Filter by job type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All job types</SelectItem>
                  {JOB_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {humanize(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="w-36" aria-label="Filter by status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {["queued", "running", "success", "partial", "failed"].map((t) => (
                    <SelectItem key={t} value={t}>
                      {humanize(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {history.error ? <ErrorBanner error={history.error} onRetry={() => history.mutate()} /> : null}
          {!history.data ? (
            <Skeleton className="h-40 w-full" />
          ) : history.data.items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">No job runs match these filters.</p>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Job</TableHead>
                    <TableHead>Trigger</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Message</TableHead>
                    <TableHead className="w-10">
                      <span className="sr-only">Details</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {history.data.items.map((j) => (
                    <JobRow key={j.id} j={j} />
                  ))}
                </TableBody>
              </Table>
              <Pagination page={history.data.page} pageSize={history.data.page_size} total={history.data.total} onPage={setPage} />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Crawl runs</CardTitle>
          <CardDescription>Per-run crawl statistics: sources checked, items seen and signals created.</CardDescription>
        </CardHeader>
        <CardContent>
          {crawls.error ? <ErrorBanner error={crawls.error} onRetry={() => crawls.mutate()} /> : null}
          {!crawls.data ? (
            <Skeleton className="h-32 w-full" />
          ) : crawls.data.items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">No crawls have run yet.</p>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Started</TableHead>
                    <TableHead>Trigger</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Sources (failed)</TableHead>
                    <TableHead className="text-right">Items seen</TableHead>
                    <TableHead className="text-right">New / changed</TableHead>
                    <TableHead className="text-right">Dupes skipped</TableHead>
                    <TableHead className="text-right">Signals</TableHead>
                    <TableHead>Duration</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {crawls.data.items.map((r) => (
                    <TableRow key={r.id} title={r.message ?? undefined}>
                      <TableCell className="whitespace-nowrap text-xs">{fmtDateTime(r.started_at)}</TableCell>
                      <TableCell>
                        <Badge tone={r.trigger === "scheduled" ? "blue" : "slate"}>{humanize(r.trigger)}</Badge>
                      </TableCell>
                      <TableCell>
                        <JobStatusBadge status={r.status} />
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {r.sources_checked} {r.sources_failed ? <span className="text-rose-400">({r.sources_failed})</span> : null}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{r.items_seen}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {r.new_items} / {r.changed_items}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{r.duplicates_skipped}</TableCell>
                      <TableCell className="text-right tabular-nums font-medium">{r.signals_created}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs">{fmtDuration(r.started_at, r.finished_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Pagination page={crawls.data.page} pageSize={crawls.data.page_size} total={crawls.data.total} onPage={setCrawlPage} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function AutomationPage() {
  return (
    <React.Suspense fallback={null}>
      <AutomationInner />
    </React.Suspense>
  );
}
