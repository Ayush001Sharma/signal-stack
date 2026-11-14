"use client";

import Link from "next/link";
import { ArrowRight, Building2, Globe, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorBanner, ListSkeleton, PageHeader } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { paths } from "@/lib/api";
import type { CompanySummary } from "@/lib/types";
import { fmtDate, hostOf, humanize, initials } from "@/lib/utils";

export default function HomePage() {
  const { data, error, isLoading, mutate } = useApi<CompanySummary[]>(paths.companies());
  return (
    <div>
      <section className="glow-card relative mb-8 overflow-hidden rounded-2xl border bg-card p-6 sm:p-10">
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-30 [mask-image:radial-gradient(ellipse_at_top_left,black,transparent_70%)]" />
        <div className="relative max-w-2xl">
          <Badge tone="default" className="mb-3">
            Company Intelligence & Executive Briefing Engine
          </Badge>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Evidence-backed intelligence, every Monday morning.</h1>
          <p className="mt-2 text-sm text-muted-foreground sm:text-base">
            Signal Stack researches your company, builds a monitored stack of customer, competitor and market sources, and turns what changes into a prioritised, cited
            executive brief.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button asChild>
              <Link href="/companies/new">
                <Plus /> Add a company
              </Link>
            </Button>
            {data && data[0] ? (
              <Button asChild variant="outline">
                <Link href={`/companies/${data[0].id}`}>
                  Open {data[0].name} <ArrowRight />
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </section>

      <PageHeader title="Companies" description="Pick a company to open its intelligence workspace." />
      {error ? <ErrorBanner error={error} onRetry={() => mutate()} /> : null}
      {isLoading ? (
        <ListSkeleton rows={3} />
      ) : data && data.length === 0 ? (
        <EmptyState
          icon={Building2}
          title="No companies yet"
          description="Add your first company. We'll research its website, discover competitors, draft interview questions and propose sources to monitor."
          action={
            <Button asChild>
              <Link href="/companies/new">
                <Plus /> Add company
              </Link>
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {(data ?? []).map((c) => (
            <Link key={c.id} href={`/companies/${c.id}`} className="group rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <Card className="h-full p-5 transition-colors group-hover:border-primary/40">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500/20 to-violet-500/20 text-sm font-semibold text-primary">
                    {initials(c.name)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <h2 className="truncate font-semibold">{c.name}</h2>
                      <Badge tone={c.status === "error" ? "rose" : c.status === "created" || c.status === "researching" ? "amber" : "emerald"}>{humanize(c.status)}</Badge>
                    </div>
                    <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-muted-foreground">
                      <Globe className="h-3 w-3" aria-hidden /> {hostOf(c.website)}
                    </p>
                    <p className="mt-3 text-xs text-muted-foreground">
                      {c.industry_label ??  "Industry not set"} · added {fmtDate(c.created_at)}
                    </p>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
