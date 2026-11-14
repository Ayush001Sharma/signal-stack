"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useSWRConfig } from "swr";
import { Bot, Cpu, KeyRound, Save, ShieldCheck, Trash2, Globe2, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Confirm } from "@/components/shared/confirm";
import { ErrorBanner, KeyValue, PageHeader } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { api, ApiError, errorMessage, fieldErrors, paths } from "@/lib/api";
import type { Company, Schedule, ScheduleUpdate, SystemInfo } from "@/lib/types";
import { fmtDateTime } from "@/lib/utils";

const TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Dubai",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Australia/Sydney",
  "Europe/London",
  "Europe/Dublin",
  "Europe/Berlin",
  "Europe/Paris",
  "Europe/Amsterdam",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
  "America/Toronto",
  "Africa/Lagos",
];
const DAYS: Array<[string, string]> = [
  ["mon", "Monday"],
  ["tue", "Tuesday"],
  ["wed", "Wednesday"],
  ["thu", "Thursday"],
  ["fri", "Friday"],
  ["sat", "Saturday"],
  ["sun", "Sunday"],
];

function ScheduleForm({ companyId }: { companyId: number }) {
  const { mutate: globalMutate } = useSWRConfig();
  const { data, error, mutate } = useApi<Schedule>(paths.schedule(companyId));
  const [f, setF] = React.useState<Schedule | null>(null);
  const [tzMode, setTzMode] = React.useState<"list" | "custom">("list");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (data && !f) {
      setF(data);
      setTzMode(TIMEZONES.includes(data.timezone) ? "list" : "custom");
    }
  }, [data, f]);

  if (error) return <ErrorBanner error={error} onRetry={() => mutate()} />;
  if (!f) return <Skeleton className="h-80 w-full" />;

  const set = <K extends keyof Schedule>(k: K, v: Schedule[K]) => setF((p) => (p ? { ...p, [k]: v } : p));
  const timeOk = (t: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(t);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!f.timezone.trim()) errs.timezone = "Required";
    if (!timeOk(f.weekly_time)) errs.weekly_time = "Use HH:MM (24h)";
    if (!timeOk(f.monthly_time)) errs.monthly_time = "Use HH:MM (24h)";
    if (!(f.monthly_day >= 1 && f.monthly_day <= 28)) errs.monthly_day = "1–28";
    if (!(f.crawl_interval_hours >= 1 && f.crawl_interval_hours <= 168)) errs.crawl_interval_hours = "1–168 hours";
    if (!(f.brief_lookback_days >= 1 && f.brief_lookback_days <= 120)) errs.brief_lookback_days = "1–120 days";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    try {
      const body: ScheduleUpdate = {
        timezone: f.timezone.trim(),
        weekly_enabled: f.weekly_enabled,
        weekly_day_of_week: f.weekly_day_of_week,
        weekly_time: f.weekly_time,
        monthly_enabled: f.monthly_enabled,
        monthly_day: f.monthly_day,
        monthly_time: f.monthly_time,
        crawl_enabled: f.crawl_enabled,
        crawl_interval_hours: f.crawl_interval_hours,
        brief_lookback_days: f.brief_lookback_days,
      };
      const saved = await api.putSchedule(companyId, body);
      setF(saved);
      await mutate(saved, { revalidate: false });
      await globalMutate((k) => typeof k === "string" && (k.startsWith("/api/scheduler") || k.startsWith(`/api/companies/${companyId}/dashboard`)));
      toast.success("Schedule saved", { description: "The scheduler was updated immediately." });
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setErrors(fieldErrors(err));
      toast.error("Could not save schedule", { description: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  const Err = ({ k }: { k: string }) => (errors[k] ? <p className="text-xs text-rose-500">{errors[k]}</p> : null);

  return (
    <form onSubmit={save} className="space-y-6" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="tz">Time zone</Label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select
            value={tzMode === "custom" ? "__custom" : f.timezone}
            onValueChange={(v) => {
              if (v === "__custom") setTzMode("custom");
              else {
                setTzMode("list");
                set("timezone", v);
              }
            }}
          >
            <SelectTrigger id="tz" className="sm:w-64">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIMEZONES.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
              <SelectItem value="__custom">Other IANA zone…</SelectItem>
            </SelectContent>
          </Select>
          {tzMode === "custom" ? <Input aria-label="Custom IANA time zone" placeholder="e.g. Pacific/Auckland" value={f.timezone} onChange={(e) => set("timezone", e.target.value)} className="sm:w-64" /> : null}
        </div>
        <Err k="timezone" />
      </div>

      <fieldset className="space-y-4 rounded-lg border p-4">
        <legend className="px-1 text-sm font-semibold">Weekly Intelligence Brief</legend>
        <div className="flex items-center gap-2">
          <Switch id="we" checked={f.weekly_enabled} onCheckedChange={(v) => set("weekly_enabled", v)} />
          <Label htmlFor="we">Enabled</Label>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="wd">Day</Label>
            <Select value={f.weekly_day_of_week} onValueChange={(v) => set("weekly_day_of_week", v)}>
              <SelectTrigger id="wd">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DAYS.map(([k, l]) => (
                  <SelectItem key={k} value={k}>
                    {l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="wt">Time</Label>
            <Input id="wt" type="time" value={f.weekly_time} onChange={(e) => set("weekly_time", e.target.value)} aria-invalid={!!errors.weekly_time} />
            <Err k="weekly_time" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lb">Lookback (days)</Label>
            <Input id="lb" type="number" min={1} max={120} value={f.brief_lookback_days} onChange={(e) => set("brief_lookback_days", Number(e.target.value))} aria-invalid={!!errors.brief_lookback_days} />
            <Err k="brief_lookback_days" />
          </div>
        </div>
      </fieldset>

      <fieldset className="space-y-4 rounded-lg border p-4">
        <legend className="px-1 text-sm font-semibold">Monthly Signal Stack Audit</legend>
        <div className="flex items-center gap-2">
          <Switch id="me" checked={f.monthly_enabled} onCheckedChange={(v) => set("monthly_enabled", v)} />
          <Label htmlFor="me">Enabled</Label>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="md">Day of month</Label>
            <Input id="md" type="number" min={1} max={28} value={f.monthly_day} onChange={(e) => set("monthly_day", Number(e.target.value))} aria-invalid={!!errors.monthly_day} />
            <Err k="monthly_day" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mt">Time</Label>
            <Input id="mt" type="time" value={f.monthly_time} onChange={(e) => set("monthly_time", e.target.value)} aria-invalid={!!errors.monthly_time} />
            <Err k="monthly_time" />
          </div>
        </div>
      </fieldset>

      <fieldset className="space-y-4 rounded-lg border p-4">
        <legend className="px-1 text-sm font-semibold">Source monitoring crawl</legend>
        <div className="flex items-center gap-2">
          <Switch id="ce" checked={f.crawl_enabled} onCheckedChange={(v) => set("crawl_enabled", v)} />
          <Label htmlFor="ce">Enabled</Label>
        </div>
        <div className="space-y-1.5 sm:w-1/3">
          <Label htmlFor="ci">Interval (hours)</Label>
          <Input id="ci" type="number" min={1} max={168} value={f.crawl_interval_hours} onChange={(e) => set("crawl_interval_hours", Number(e.target.value))} aria-invalid={!!errors.crawl_interval_hours} />
          <Err k="crawl_interval_hours" />
        </div>
      </fieldset>

      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">Last updated {fmtDateTime(f.updated_at)}</span>
        <Button type="submit" loading={saving}>
          <Save /> Save schedule
        </Button>
      </div>
    </form>
  );
}

function CompanyForm({ company }: { company: Company }) {
  const { mutate } = useSWRConfig();
  const [f, setF] = React.useState({ name: company.name, industry: company.industry ?? "", business_context: company.business_context ?? "" });
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (f.name.trim().length < 2) errs.name = "At least 2 characters";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    try {
      await api.updateCompany(company.id, { name: f.name.trim(), industry: f.industry.trim() || null, business_context: f.business_context.trim() || null });
      toast.success("Company updated", { description: "To re-score sources for a new context, use “Change business context” on the Profile page." });
      await mutate((k) => typeof k === "string" && (k === paths.companies() || k.startsWith(`/api/companies/${company.id}`)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setErrors(fieldErrors(err));
      toast.error("Could not update company", { description: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="space-y-4" noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="cn">Name</Label>
          <Input id="cn" value={f.name} maxLength={200} onChange={(e) => setF({ ...f, name: e.target.value })} aria-invalid={!!errors.name} />
          {errors.name ? <p className="text-xs text-rose-500">{errors.name}</p> : null}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ci2">Industry</Label>
          <Input id="ci2" value={f.industry} maxLength={200} onChange={(e) => setF({ ...f, industry: e.target.value })} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="cb">Business context</Label>
        <Textarea id="cb" rows={4} maxLength={4000} value={f.business_context} onChange={(e) => setF({ ...f, business_context: e.target.value })} />
      </div>
      <div className="flex justify-end">
        <Button type="submit" loading={saving}>
          <Save /> Save company
        </Button>
      </div>
    </form>
  );
}

function SystemInfoCard() {
  const { data, error, mutate } = useApi<SystemInfo>(paths.system());
  if (error) return <ErrorBanner error={error} onRetry={() => mutate()} />;
  if (!data) return <Skeleton className="h-64 w-full" />;
  const Row = ({ icon: Icon, title, value, help }: { icon: React.ComponentType<{ className?: string }>; title: string; value: React.ReactNode; help: string }) => (
    <div className="flex gap-3 border-b py-3 last:border-0">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium">{title}</p>
          <div className="text-sm">{value}</div>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{help}</p>
      </div>
    </div>
  );
  return (
    <div>
      <Row
        icon={Bot}
        title="Local LLM"
        value={
          <Badge tone={data.llm.available ? "emerald" : "slate"}>
            {data.llm.available ? `${data.llm.provider ?? "LLM"} · ${data.llm.model ?? ""}` : "Unavailable"}
          </Badge>
        }
        help="Optional. Used only to phrase interview questions, summaries and interpretations. Scores, evidence and verification never depend on it; everything falls back to transparent rules."
      />
      <Row icon={Cpu} title="Embeddings backend" value={<Badge tone="blue">{data.embeddings}</Badge>} help="Semantic similarity used for relevance scoring, name-collision filtering and duplicate detection." />
      <Row
        icon={KeyRound}
        title="API authentication"
        value={<Badge tone={data.auth === "api_key" ? "emerald" : "amber"}>{data.auth}</Badge>}
        help="When an API key is configured on the backend, set NEXT_PUBLIC_API_KEY for this UI so requests send X-API-Key."
      />
      <Row
        icon={ShieldCheck}
        title="Crawler policy"
        value={<Badge tone="emerald">{data.crawler.respects_robots_txt ? "Respects robots.txt" : "robots.txt ignored"}</Badge>}
        help={`User agent “${data.crawler.user_agent}”. ${data.crawler.per_host_delay_seconds}s delay per host, ${data.crawler.timeout_seconds}s timeout, ${data.crawler.max_retries} retries.`}
      />
      <Row
        icon={Globe2}
        title="Reddit API"
        value={<Badge tone={data.reddit_api_configured ? "emerald" : "slate"}>{data.reddit_api_configured ? "Configured" : "Not configured"}</Badge>}
        help="Reddit sources are only crawled through the official API with credentials; otherwise they are skipped."
      />
      <Row
        icon={Database}
        title="Platform"
        value={
          <span className="text-xs text-muted-foreground">
            {data.app} · {data.environment} · scheduler {data.scheduler.running ? "running" : "stopped"}
          </span>
        }
        help={`Upload limit ${data.upload_limit_mb} MB. Totals: ${Object.entries(data.counts)
          .map(([k, v]) => `${v} ${k.replace("_", " ")}`)
          .join(", ")}.`}
      />
    </div>
  );
}

export default function SettingsPage() {
  const id = useCompanyId();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const company = useApi<Company>(paths.company(id));
  const [confirmName, setConfirmName] = React.useState("");

  const del = async () => {
    try {
      await api.deleteCompany(id);
      toast.success("Company deleted");
      await mutate(paths.companies());
      router.push("/");
    } catch (e) {
      toast.error("Could not delete company", { description: errorMessage(e) });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Settings" title="Settings" description="Schedules, company basics and system configuration." />
      <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Schedule</CardTitle>
              <CardDescription>When the weekly brief, monthly audit and monitoring crawl run for this company.</CardDescription>
            </CardHeader>
            <CardContent>
              <ScheduleForm companyId={id} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Company profile basics</CardTitle>
              <CardDescription>Edits here update the profile directly without re-scoring sources.</CardDescription>
            </CardHeader>
            <CardContent>{company.error ? <ErrorBanner error={company.error} onRetry={() => company.mutate()} /> : company.data ? <CompanyForm key={company.data.id} company={company.data} /> : <Skeleton className="h-48 w-full" />}</CardContent>
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>System</CardTitle>
              <CardDescription>Read-only backend configuration.</CardDescription>
            </CardHeader>
            <CardContent>
              <SystemInfoCard />
            </CardContent>
          </Card>
          <Card className="border-rose-500/30">
            <CardHeader>
              <CardTitle className="text-rose-500">Danger zone</CardTitle>
              <CardDescription>Deleting a company permanently removes its profile, sources, signals, briefs and schedule.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <dl>
                <KeyValue label="Company">{company.data?.name ?? "…"}</KeyValue>
              </dl>
              <div className="space-y-1.5">
                <Label htmlFor="confirm-name">Type the company name to enable deletion</Label>
                <Input id="confirm-name" value={confirmName} onChange={(e) => setConfirmName(e.target.value)} placeholder={company.data?.name} />
              </div>
              <Confirm
                title={`Delete ${company.data?.name ?? "company"}?`}
                description="This cannot be undone. All intelligence data for this company will be permanently deleted."
                confirmLabel="Delete permanently"
                onConfirm={del}
              >
                <Button variant="destructive" disabled={!company.data || confirmName.trim() !== company.data.name}>
                  <Trash2 /> Delete company
                </Button>
              </Confirm>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
