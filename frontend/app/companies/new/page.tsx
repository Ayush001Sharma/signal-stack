"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowRight, Check, Circle, Globe, Loader2, MessagesSquare, Radar, Search, Swords, XCircle, RefreshCw } from "lucide-react";
import { useSWRConfig } from "swr";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { PageHeader } from "@/components/shared/states";
import { JobStatusBadge } from "@/components/shared/badges";
import { useApi } from "@/hooks/use-api";
import { api, ApiError, errorMessage, fieldErrors, paths } from "@/lib/api";
import type { Company, Competitor, InterviewState, JobRun, Page, Source } from "@/lib/types";
import { cn, fmtDuration } from "@/lib/utils";

const STEPS = [
  { key: "research", label: "Researching website", desc: "Crawling public pages, extracting products, segments, geographies and keywords.", icon: Search },
  { key: "competitors", label: "Discovering competitors", desc: "Finding direct competitors and substitutes from co-mentions in news.", icon: Swords },
  { key: "interview", label: "Drafting interview", desc: "Generating adaptive founder questions to fill the gaps research can't see.", icon: MessagesSquare },
  { key: "sources", label: "Proposing sources", desc: "Probing feeds, news searches and communities to build your Signal Stack.", icon: Radar },
] as const;

function SetupProgress({ companyId }: { companyId: number }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [retrying, setRetrying] = React.useState(false);
  const jobs = useApi<Page<JobRun>>(paths.jobs({ company_id: companyId, job_type: "setup", page_size: 1 }), { refreshInterval: (d) => (d?.items[0] && ["queued", "running"].includes(d.items[0].status) ? 2000 : 0) });
  const job = jobs.data?.items[0];
  const active = !job || job.status === "queued" || job.status === "running";
  const refresh = active ? 2500 : 0;
  const company = useApi<Company>(paths.company(companyId), { refreshInterval: refresh });
  const comps = useApi<Competitor[]>(paths.competitors(companyId), { refreshInterval: refresh });
  const interview = useApi<InterviewState>(paths.interview(companyId), { refreshInterval: refresh });
  const sources = useApi<Source[]>(paths.sources(companyId), { refreshInterval: refresh });

  const done = job?.status === "success" || job?.status === "partial";
  const failed = job?.status === "failed";
  const researched = !!company.data && !["created", "researching"].includes(company.data.status);
  const nComps = comps.data?.length ?? 0;
  const nQs = interview.data?.questions.length ?? 0;
  const nSources = sources.data?.length ?? 0;

  let current = 0;
  if (done) current = 4;
  else if (nQs > 0) current = 3;
  else if (nComps > 0) current = 2;
  else if (researched) current = 1;

  React.useEffect(() => {
    if (done) {
      void mutate((k) => typeof k === "string" && k.startsWith("/api/companies"));
      toast.success("Setup complete", { description: job?.message ?? undefined });
      const t = setTimeout(() => router.push(`/companies/${companyId}/profile`), 2500);
      return () => clearTimeout(t);
    }
  }, [done, companyId, router, job?.message, mutate]);

  const retry = async () => {
    setRetrying(true);
    try {
      await api.rerunSetup(companyId);
      await jobs.mutate();
      toast.success("Setup restarted");
    } catch (e) {
      toast.error("Could not restart setup", { description: errorMessage(e) });
    } finally {
      setRetrying(false);
    }
  };

  const counts = [
    researched ? `${company.data?.research_summary?.pages_crawled?.length ?? 0} pages crawled · ${company.data?.keywords.length ?? 0} keywords` : null,
    nComps ? `${nComps} competitors found` : null,
    nQs ? `${nQs} questions drafted` : null,
    nSources ? `${nSources} sources proposed` : null,
  ];

  return (
    <Card className="glow-card">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Setting up {company.data?.name ?? "company"}</CardTitle>
          {job ? <JobStatusBadge status={job.status} /> : <JobStatusBadge status="queued" />}
        </div>
        <CardDescription>
          This usually takes a few minutes. You can leave this page — setup continues in the background{job ? ` (job #${job.id})` : ""}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Progress value={(current / 4) * 100} className="mb-6" aria-label="Setup progress" />
        <ol className="space-y-4">
          {STEPS.map((s, i) => {
            const state = failed && i === current ? "failed" : i < current ? "done" : i === current && !done ? "active" : "todo";
            return (
              <li key={s.key} className="flex gap-3">
                <div
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
                    state === "done" && "border-emerald-500/40 bg-emerald-500/15 text-emerald-500",
                    state === "active" && "border-primary/40 bg-primary/15 text-primary",
                    state === "failed" && "border-rose-500/40 bg-rose-500/15 text-rose-500",
                    state === "todo" && "text-muted-foreground",
                  )}
                  aria-hidden
                >
                  {state === "done" ? <Check className="h-4 w-4" /> : state === "active" ? <Loader2 className="h-4 w-4 animate-spin" /> : state === "failed" ? <XCircle className="h-4 w-4" /> : <Circle className="h-3 w-3" />}
                </div>
                <div className="min-w-0">
                  <p className={cn("text-sm font-medium", state === "todo" && "text-muted-foreground")}>
                    {i + 1}. {s.label}
                    <span className="sr-only"> — {state}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">{s.desc}</p>
                  {counts[i] ? <p className="mt-1 text-xs text-primary">{counts[i]}</p> : null}
                </div>
              </li>
            );
          })}
        </ol>
        {failed ? (
          <div role="alert" className="mt-6 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm">
            <p className="font-medium text-rose-500">Setup failed</p>
            <p className="mt-1 text-muted-foreground">{job?.message}</p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" variant="outline" loading={retrying} onClick={retry}>
                <RefreshCw /> Retry setup
              </Button>
              <Button size="sm" variant="ghost" asChild>
                <Link href={`/companies/${companyId}/profile`}>Open profile anyway</Link>
              </Button>
            </div>
          </div>
        ) : null}
        {done ? (
          <div className="mt-6 flex flex-wrap items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
            <Check className="h-4 w-4 text-emerald-500" aria-hidden />
            <span className="flex-1">
              {job?.message} {job ? `(${fmtDuration(job.started_at, job.finished_at)})` : ""} Redirecting to the profile…
            </span>
            <Button size="sm" asChild>
              <Link href={`/companies/${companyId}/profile`}>
                Open profile <ArrowRight />
              </Link>
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function NewCompanyInner() {
  const search = useSearchParams();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const watching = search.get("setup");
  const [form, setForm] = React.useState({ name: "", website: "", industry: "", business_context: "" });
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const validate = () => {
    const e: Record<string, string> = {};
    if (form.name.trim().length < 2) e.name = "Enter the company name (at least 2 characters).";
    if (!/^https?:\/\/[^\s.]+\.[^\s]+$/i.test(form.website.trim())) e.website = "Enter a full URL, e.g. https://example.com";
    if (form.business_context.length > 4000) e.business_context = "Keep business context under 4000 characters.";
    if (form.industry.length > 200) e.industry = "Keep industry under 200 characters.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setFormError(null);
    if (!validate()) return;
    setSubmitting(true);
    try {
      const c = await api.createCompany({
        name: form.name.trim(),
        website: form.website.trim(),
        industry: form.industry.trim() || null,
        business_context: form.business_context.trim() || null,
        run_setup: true,
      });
      toast.success(`${c.name} created`, { description: "Research and setup have started." });
      await mutate(paths.companies());
      router.replace(`/companies/new?setup=${c.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        const fe = fieldErrors(e);
        setErrors(fe);
        setFormError(Object.keys(fe).length ? "Please fix the highlighted fields." : e.message);
      } else if (e instanceof ApiError && e.status === 409) {
        setFormError(e.message);
        setErrors({ website: "A company with this domain already exists." });
      } else {
        setFormError(errorMessage(e));
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (watching) {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader eyebrow="Company setup" title="Building your intelligence profile" description="Research → competitors → interview → sources. Every fact is stored with its evidence." />
        <SetupProgress companyId={Number(watching)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader eyebrow="Company setup" title="Add a company" description="We'll research the public website, then you can confirm facts, answer a short founder interview and approve sources." />
      <Card>
        <form onSubmit={submit} noValidate>
          <CardContent className="space-y-5 p-6">
            {formError ? (
              <div role="alert" className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-600 dark:text-rose-300">
                {formError}
              </div>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="name">Company name *</Label>
              <Input id="name" value={form.name} onChange={set("name")} placeholder="Acme Analytics" aria-invalid={!!errors.name} aria-describedby={errors.name ? "name-err" : undefined} required />
              {errors.name ? <p id="name-err" className="text-xs text-rose-500">{errors.name}</p> : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="website">Website *</Label>
              <div className="relative">
                <Globe className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
                <Input
                  id="website"
                  className="pl-9"
                  value={form.website}
                  onChange={set("website")}
                  placeholder="https://acme.com"
                  inputMode="url"
                  aria-invalid={!!errors.website}
                  aria-describedby={errors.website ? "website-err" : "website-help"}
                  required
                />
              </div>
              {errors.website ? (
                <p id="website-err" className="text-xs text-rose-500">{errors.website}</p>
              ) : (
                <p id="website-help" className="text-xs text-muted-foreground">Only robots.txt-permitted public pages are crawled.</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="industry">Industry (optional)</Label>
              <Input id="industry" value={form.industry} onChange={set("industry")} placeholder="e.g. Fintech — payments infrastructure" aria-invalid={!!errors.industry} />
              {errors.industry ? <p className="text-xs text-rose-500">{errors.industry}</p> : <p className="text-xs text-muted-foreground">Leave blank and we’ll classify it from the website (marked as an assumption).</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="ctx">Business context (optional)</Label>
              <Textarea
                id="ctx"
                rows={4}
                value={form.business_context}
                onChange={set("business_context")}
                placeholder="What you sell, to whom, where — and what you most want to keep an eye on."
                aria-invalid={!!errors.business_context}
              />
              {errors.business_context ? <p className="text-xs text-rose-500">{errors.business_context}</p> : null}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => router.back()}>
                Cancel
              </Button>
              <Button type="submit" loading={submitting}>
                Create & start research <ArrowRight />
              </Button>
            </div>
          </CardContent>
        </form>
      </Card>
    </div>
  );
}

export default function NewCompanyPage() {
  return (
    <React.Suspense fallback={null}>
      <NewCompanyInner />
    </React.Suspense>
  );
}
