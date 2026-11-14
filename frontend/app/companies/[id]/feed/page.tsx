"use client";

import * as React from "react";
import { Filter, Newspaper, Radar, RotateCcw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EmptyState, ErrorBanner, ListSkeleton, PageHeader, Pagination } from "@/components/shared/states";
import { VERIFICATION_LABEL } from "@/components/shared/badges";
import { SignalCard } from "@/components/signal-card";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, paths } from "@/lib/api";
import type { Facets, Page, Signal } from "@/lib/types";
import { humanize } from "@/lib/utils";

const DEFAULTS = {
  category: "all",
  competitor_id: "all",
  priority: "all",
  polarity: "all",
  verification_status: "all",
  signal_type: "all",
  min_relevance: 0,
  min_impact: 0,
  date_from: "",
  date_to: "",
  sort: "priority",
  meaningful_only: true,
  include_dismissed: false,
};
type FiltersState = typeof DEFAULTS;

function FacetSelect({ id, label, value, onChange, options, render }: { id: string; label: string; value: string; onChange: (v: string) => void; options: Record<string, number> | Array<{ id: number; name: string }>; render?: (k: string) => string }) {
  const entries: Array<[string, string]> = Array.isArray(options) ? options.map((o) => [String(o.id), o.name]) : Object.entries(options).map(([k, n]) => [k, `${render ? render(k) : humanize(k)} (${n})`]);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All</SelectItem>
          {entries.map(([k, l]) => (
            <SelectItem key={k} value={k}>
              {l}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default function FeedPage() {
  const id = useCompanyId();
  const jobs = useJobRunner(id);
  const [f, setF] = React.useState<FiltersState>(DEFAULTS);
  const [q, setQ] = React.useState("");
  const [qd, setQd] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [showFilters, setShowFilters] = React.useState(true);

  React.useEffect(() => {
    const t = setTimeout(() => setQd(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);
  React.useEffect(() => setPage(1), [f, qd]);

  const set = <K extends keyof FiltersState>(k: K, v: FiltersState[K]) => setF((p) => ({ ...p, [k]: v }));
  const a = (v: string) => (v === "all" ? undefined : v);

  const facets = useApi<Facets>(paths.facets(id));
  const key = paths.signals(id, {
    category: a(f.category),
    competitor_id: a(f.competitor_id),
    priority: a(f.priority),
    polarity: a(f.polarity),
    verification_status: a(f.verification_status),
    signal_type: a(f.signal_type),
    min_relevance: f.min_relevance > 0 ? f.min_relevance / 100 : undefined,
    min_impact: f.min_impact > 0 ? f.min_impact / 100 : undefined,
    date_from: f.date_from ? `${f.date_from}T00:00:00` : undefined,
    date_to: f.date_to ? `${f.date_to}T23:59:59` : undefined,
    q: qd || undefined,
    sort: f.sort,
    meaningful_only: f.meaningful_only,
    include_dismissed: f.include_dismissed,
    page,
    page_size: 20,
  });
  const { data, error, isLoading, mutate } = useApi<Page<Signal>>(key, { keepPreviousData: true });
  const fc = facets.data;
  const dirty = JSON.stringify(f) !== JSON.stringify(DEFAULTS) || !!qd;

  return (
    <div>
      <PageHeader
        eyebrow="Intelligence feed"
        title="Signals"
        description="Every signal links to its evidence. Reliability, evidence strength and relevance are scored separately; interpretation is labelled."
        actions={
          <Button variant="outline" className="lg:hidden" onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters} aria-controls="feed-filters">
            <Filter /> {showFilters ? "Hide" : "Show"} filters
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <aside id="feed-filters" className={showFilters ? "block" : "hidden lg:block"} aria-label="Signal filters">
          <Card className="space-y-4 p-4 lg:sticky lg:top-20">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
              <Input className="pl-9" placeholder="Search title, text, publisher" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search signals" maxLength={200} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sort">Sort by</Label>
              <Select value={f.sort} onValueChange={(v) => set("sort", v)}>
                <SelectTrigger id="sort">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="priority">Priority score</SelectItem>
                  <SelectItem value="date">Event date</SelectItem>
                  <SelectItem value="discovered">Discovered date</SelectItem>
                  <SelectItem value="relevance">Relevance</SelectItem>
                  <SelectItem value="impact">Impact</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <FacetSelect id="f-cat" label="Category" value={f.category} onChange={(v) => set("category", v)} options={fc?.category ?? {}} />
            <FacetSelect id="f-comp" label="Competitor" value={f.competitor_id} onChange={(v) => set("competitor_id", v)} options={fc?.competitors ?? []} />
            <FacetSelect id="f-pri" label="Priority" value={f.priority} onChange={(v) => set("priority", v)} options={fc?.priority ?? {}} />
            <FacetSelect id="f-pol" label="Polarity" value={f.polarity} onChange={(v) => set("polarity", v)} options={fc?.polarity ?? {}} />
            <FacetSelect id="f-ver" label="Verification" value={f.verification_status} onChange={(v) => set("verification_status", v)} options={fc?.verification_status ?? {}} render={(k) => VERIFICATION_LABEL[k] ?? humanize(k)} />
            <FacetSelect id="f-type" label="Signal type" value={f.signal_type} onChange={(v) => set("signal_type", v)} options={fc?.signal_type ?? {}} />
            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <Label>Min. strategic relevance</Label>
                <span className="tabular-nums text-muted-foreground">{f.min_relevance}%</span>
              </div>
              <Slider value={[f.min_relevance]} max={100} step={5} onValueChange={([v]) => set("min_relevance", v)} thumbLabel="Minimum relevance" />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <Label>Min. impact</Label>
                <span className="tabular-nums text-muted-foreground">{f.min_impact}%</span>
              </div>
              <Slider value={[f.min_impact]} max={100} step={5} onValueChange={([v]) => set("min_impact", v)} thumbLabel="Minimum impact" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="df">From</Label>
                <Input id="df" type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="dt">To</Label>
                <Input id="dt" type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value)} />
              </div>
            </div>
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="mo" className="leading-snug">
                Meaningful only
                <span className="block text-[11px] font-normal text-muted-foreground">Hide low-relevance noise</span>
              </Label>
              <Switch id="mo" checked={f.meaningful_only} onCheckedChange={(v) => set("meaningful_only", v)} />
            </div>
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="id">Include dismissed</Label>
              <Switch id="id" checked={f.include_dismissed} onCheckedChange={(v) => set("include_dismissed", v)} />
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              disabled={!dirty}
              onClick={() => {
                setF(DEFAULTS);
                setQ("");
              }}
            >
              <RotateCcw /> Reset filters
            </Button>
            {fc ? (
              <p className="text-[11px] text-muted-foreground">
                {fc.total_collected} signals scored from {fc.raw_items} collected items.
              </p>
            ) : null}
          </Card>
        </aside>

        <section aria-label="Signals" aria-busy={isLoading}>
          {error ? <ErrorBanner error={error} onRetry={() => mutate()} /> : null}
          {data ? (
            <p className="mb-3 text-sm text-muted-foreground" aria-live="polite">
              {data.total} signal{data.total === 1 ? "" : "s"}
            </p>
          ) : null}
          {isLoading && !data ? (
            <ListSkeleton rows={4} />
          ) : data && data.items.length === 0 ? (
            dirty ? (
              <EmptyState
                icon={Filter}
                title="No signals match these filters"
                description="Loosen the filters or turn off “meaningful only” to see lower-relevance items."
                action={
                  <Button
                    variant="outline"
                    onClick={() => {
                      setF(DEFAULTS);
                      setQ("");
                    }}
                  >
                    <RotateCcw /> Reset filters
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon={Newspaper}
                title="No signals yet"
                description="Signals are created when a monitoring crawl collects new items from approved sources and scores them against your profile."
                action={
                  <Button loading={jobs.isRunning("crawl")} onClick={() => jobs.run("crawl", "Crawl", () => api.crawlNow(id))}>
                    <Radar /> Run crawl now
                  </Button>
                }
              />
            )
          ) : (
            <div className="space-y-4">
              {(data?.items ?? []).map((s) => (
                <SignalCard key={s.id} signal={s} companyId={id} onChanged={() => mutate()} />
              ))}
            </div>
          )}
          {data ? <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => { setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} /> : null}
        </section>
      </div>
    </div>
  );
}
