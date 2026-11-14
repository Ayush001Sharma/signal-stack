"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  FileText,
  Flame,
  Lightbulb,
  Play,
  Radar,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CardsSkeleton, EmptyState, ErrorBanner, PageHeader, StatCard } from "@/components/shared/states";
import { JobStatusBadge } from "@/components/shared/badges";
import { HealthDonut, SignalTrendChart } from "@/components/charts";
import { SignalMini } from "@/components/signal-card";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, paths } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import { describeTrigger, fmtDate, fmtDateTime, fmtRelative, humanize } from "@/lib/utils";

const JOB_LABEL: Record<string, string> = { crawl: "Monitoring crawl", weekly_brief: "Weekly Intelligence Brief", monthly_audit: "Monthly Signal Stack Audit" };

export default function OverviewPage() {
  const id = useCompanyId();
  const { data, error, isLoading, mutate } = useApi<Dashboard>(paths.dashboard(id), { refreshInterval: 30000 });
  const jobs = useJobRunner(id);

  const actions = (
    <>
      <Button variant="outline" loading={jobs.isRunning("crawl")} onClick={() => jobs.run("crawl", "Crawl", () => api.crawlNow(id))}>
        <Radar /> Run crawl now
      </Button>
      <Button loading={jobs.isRunning("brief")} onClick={() => jobs.run("brief", "Monday Brief", () => api.generateBrief(id, {}))}>
        <Sparkles /> Generate brief now
      </Button>
    </>
  );

  if (error && !data) {
    return (
      <div>
        <PageHeader title="Overview" />
        <ErrorBanner error={error} onRetry={() => mutate()} />
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div>
        <PageHeader title="Overview" description="Loading the latest intelligence…" />
        <CardsSkeleton count={8} />
      </div>
    );
  }

  const d = data;
  const healthTotal = Object.values(d.sources.health).reduce((a, b) => a + b, 0);
  const noSources = d.sources.approved === 0;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Overview" title={d.company.name} description={`${d.company.industry_label ??  "Industry not set"} · ${d.company.website}`} actions={actions} />

      {d.failed_jobs.length > 0 ? (
        <div role="alert" className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-rose-600 dark:text-rose-300">
                {d.failed_jobs.length} recent job{d.failed_jobs.length > 1 ? "s" : ""} failed
              </p>
              <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                {d.failed_jobs.slice(0, 3).map((j) => (
                  <li key={j.id} className="truncate">
                    #{j.id} {humanize(j.job_type)} · {fmtDateTime(j.started_at)} — {j.message ?? j.error?.split("\n")[0]}
                  </li>
                ))}
              </ul>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link href={`/companies/${id}/automation?status=failed`}>View</Link>
            </Button>
          </div>
        </div>
      ) : null}

      {/* Hero */}
      <Card className="glow-card overflow-hidden">
        <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-primary">This week</p>
            <div className="mt-2 flex items-end gap-3">
              <span className="text-4xl font-semibold tabular-nums tracking-tight">{d.signals.new_this_week}</span>
              <span className="pb-1 text-sm text-muted-foreground">new meaningful signals</span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              {d.signals.total_meaningful} meaningful signals from {d.signals.raw_items} collected items across {d.sources.approved} approved sources.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(d.signals.by_category).map(([k, v]) => (
                <Badge key={k} tone="outline" className="text-xs">
                  {humanize(k)}: {v}
                </Badge>
              ))}
            </div>
          </div>
          <div className="rounded-xl border bg-background/40 p-4">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 text-sm font-medium">
                <FileText className="h-4 w-4 text-primary" aria-hidden /> Latest Monday Brief
              </p>
              {d.latest_brief ? <Badge tone="slate">{humanize(d.latest_brief.trigger)}</Badge> : null}
            </div>
            {d.latest_brief ? (
              <>
                <p className="mt-2 line-clamp-2 text-sm">{d.latest_brief.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {fmtDate(d.latest_brief.period_start)} → {fmtDate(d.latest_brief.period_end)} · {d.latest_brief.stats.meaningful_signals ?? 0} signals ·{" "}
                  {d.latest_brief.stats.high_priority ?? 0} high priority
                </p>
                <Button size="sm" className="mt-3" asChild>
                  <Link href={`/companies/${id}/briefs/${d.latest_brief.id}`}>
                    Read brief <ArrowRight />
                  </Link>
                </Button>
              </>
            ) : (
              <>
                <p className="mt-2 text-sm text-muted-foreground">No brief has been generated yet. Generate one now, or wait for the scheduled Monday run.</p>
                <Button size="sm" className="mt-3" loading={jobs.isRunning("brief")} onClick={() => jobs.run("brief", "Monday Brief", () => api.generateBrief(id, {}))}>
                  <Sparkles /> Generate brief
                </Button>
              </>
            )}
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 2xl:grid-cols-6">
        <StatCard label="Monitored sources" value={d.sources.approved} hint="Approved & monitored" icon={Radar} />
        <StatCard label="Pending sources" value={d.sources.pending} hint="Awaiting your approval" icon={Clock} tone="amber" />
        <StatCard label="New this week" value={d.signals.new_this_week} hint="Meaningful signals" icon={TrendingUp} tone="violet" />
        <StatCard label="High priority" value={d.signals.high_priority} hint="Score ≥ 60" icon={Flame} tone="rose" />
        <StatCard label="Opportunities" value={d.signals.opportunities} icon={Lightbulb} tone="emerald" />
        <StatCard label="Risks" value={d.signals.risks} icon={ShieldAlert} tone="rose" />
      </div>

      {noSources ? (
        <EmptyState
          icon={Radar}
          title="No approved sources yet"
          description={
            d.sources.pending > 0
              ? `${d.sources.pending} sources are waiting for approval. Approve them so monitoring crawls can collect signals.`
              : "Sources are proposed during setup. If setup is still running, check back in a few minutes."
          }
          action={
            <Button asChild>
              <Link href={`/companies/${id}/sources?approval=pending`}>Review sources</Link>
            </Button>
          }
        />
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Signal trend by category</CardTitle>
            <CardDescription>Meaningful signals per day (event date, or discovery date if undated), last 30 days.</CardDescription>
          </CardHeader>
          <CardContent>
            {d.signal_trend.length ? (
              <SignalTrendChart data={d.signal_trend} />
            ) : (
              <EmptyState
                className="py-8"
                icon={TrendingUp}
                title="No signals in the last 30 days"
                description="Signals appear after a monitoring crawl collects and scores new items from approved sources."
                action={
                  <Button size="sm" variant="outline" loading={jobs.isRunning("crawl")} onClick={() => jobs.run("crawl", "Crawl", () => api.crawlNow(id))}>
                    <Play /> Run crawl now
                  </Button>
                }
              />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Source health</CardTitle>
            <CardDescription>Approved sources by latest crawl health.</CardDescription>
          </CardHeader>
          <CardContent>
            {healthTotal ? (
              <HealthDonut health={d.sources.health} />
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">No approved sources to report on yet.</p>
            )}
            <Button variant="link" size="sm" className="mt-2 px-0" asChild>
              <Link href={`/companies/${id}/health`}>
                Health & audit <ArrowRight />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Top signals</CardTitle>
              <CardDescription>Highest priority meaningful signals right now.</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/companies/${id}/feed`}>
                Open feed <ArrowRight />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {d.top_signals.length ? (
              <div className="divide-y">
                {d.top_signals.map((s) => (
                  <SignalMini key={s.id} signal={s} companyId={id} />
                ))}
              </div>
            ) : (
              <p className="py-6 text-center text-sm text-muted-foreground">No meaningful signals yet. They will appear after the first monitoring crawl.</p>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarClock className="h-4 w-4 text-primary" aria-hidden /> Upcoming scheduled jobs
              </CardTitle>
              <CardDescription>Times shown in your local time zone.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {d.upcoming_jobs.length ? (
                d.upcoming_jobs.map((j) => (
                  <div key={j.id} className="flex items-start justify-between gap-3 text-sm">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{JOB_LABEL[j.job_type] ?? j.name}</p>
                      <p className="text-xs text-muted-foreground">{describeTrigger(j.trigger)}</p>
                    </div>
                    <div className="shrink-0 text-right text-xs">
                      <p>{fmtDateTime(j.next_run_time, "Paused")}</p>
                      <p className="text-muted-foreground">{j.next_run_time ? fmtRelative(j.next_run_time) : ""}</p>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No scheduled jobs — automation is disabled.</p>
              )}
              <Button variant="link" size="sm" className="px-0" asChild>
                <Link href={`/companies/${id}/automation`}>
                  Automation <ArrowRight />
                </Link>
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary" aria-hidden /> Recent monitoring activity
              </CardTitle>
            </CardHeader>
            <CardContent>
              {d.recent_activity.length ? (
                <ol className="space-y-3">
                  {d.recent_activity.map((a, i) => (
                    <li key={i} className="flex items-start justify-between gap-3 text-sm">
                      <div className="min-w-0">
                        <p className="font-medium">{humanize(a.kind)}</p>
                        <p className="line-clamp-2 text-xs text-muted-foreground">{a.message ?? "—"}</p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <JobStatusBadge status={a.status} />
                        <span className="text-[11px] text-muted-foreground">{fmtRelative(a.at)}</span>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-muted-foreground">No activity yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
