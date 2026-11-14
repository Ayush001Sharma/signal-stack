"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  Check,
  Copy,
  Eye,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  Radar,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Wand2,
  X,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Confirm } from "@/components/shared/confirm";
import { ApprovalBadge, CategoryBadge, HealthBadge, JobStatusBadge, MonitoringBadge } from "@/components/shared/badges";
import { EvidenceLink } from "@/components/shared/links";
import { EmptyState, ErrorBanner, KeyValue, PageHeader } from "@/components/shared/states";
import { SourceCard } from "@/components/source-card";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, ApiError, errorMessage, fieldErrors, paths } from "@/lib/api";
import type { Competitor, CrawlLog, Duplicate, RawItem, Source } from "@/lib/types";
import { fmtDate, fmtDateTime, fmtRelative, humanize, pct } from "@/lib/utils";

const SOURCE_TYPES = ["rss", "news_search", "web_page", "stackexchange", "hackernews", "federal_register", "govuk", "reddit"];
const HEALTH = ["healthy", "degraded", "failing", "dead", "blocked", "unknown"];

function SourceDetails({ companyId, source, open, onOpenChange }: { companyId: number; source: Source | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const sid = source?.id;
  const history = useApi<CrawlLog[]>(open && sid ? paths.sourceHistory(companyId, sid) : null);
  const items = useApi<RawItem[]>(open && sid ? paths.sourceItems(companyId, sid) : null);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto p-6 sm:max-w-2xl">
        {source ? (
          <>
            <SheetHeader>
              <SheetTitle>{source.name}</SheetTitle>
              <SheetDescription asChild>
                <div>
                  <EvidenceLink url={source.url} companyId={companyId} className="text-xs" />
                </div>
              </SheetDescription>
            </SheetHeader>
            <Tabs defaultValue="overview">
              <TabsList>
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="history">Crawl history</TabsTrigger>
                <TabsTrigger value="items">Collected items</TabsTrigger>
              </TabsList>
              <TabsContent value="overview" className="space-y-4">
                <SourceCard source={source} companyId={companyId} />
                <dl className="grid grid-cols-2 gap-4 text-sm">
                  <KeyValue label="Discovered by">{humanize(source.discovered_by)}</KeyValue>
                  <KeyValue label="Added">{fmtDateTime(source.created_at)}</KeyValue>
                  <KeyValue label="Last success">{fmtDateTime(source.last_success_at, "Never")}</KeyValue>
                  <KeyValue label="Last new item">{fmtDateTime(source.last_new_item_at, "Never")}</KeyValue>
                  <KeyValue label="Consecutive failures">{source.consecutive_failures}</KeyValue>
                  <KeyValue label="Duplicate of">{source.duplicate_of_id ? `Source #${source.duplicate_of_id}` : "—"}</KeyValue>
                  {source.query ? <KeyValue label="Search query">{source.query}</KeyValue> : null}
                  {source.description ? <KeyValue label="Description">{source.description}</KeyValue> : null}
                </dl>
                {source.last_error ? (
                  <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs">
                    <p className="mb-1 font-medium text-rose-500">Last error</p>
                    <p className="break-words font-mono">{source.last_error}</p>
                  </div>
                ) : null}
              </TabsContent>
              <TabsContent value="history">
                {history.error ? <ErrorBanner error={history.error} onRetry={() => history.mutate()} /> : null}
                {!history.data ? (
                  <Skeleton className="h-32 w-full" />
                ) : history.data.length === 0 ? (
                  <p className="py-6 text-center text-sm text-muted-foreground">This source has not been crawled yet.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>When</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">HTTP</TableHead>
                        <TableHead className="text-right">Found / new / changed</TableHead>
                        <TableHead className="text-right">Duration</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {history.data.map((l) => (
                        <React.Fragment key={l.id}>
                          <TableRow>
                            <TableCell className="whitespace-nowrap text-xs">{fmtDateTime(l.started_at)}</TableCell>
                            <TableCell>
                              <JobStatusBadge status={l.status} />
                            </TableCell>
                            <TableCell className="text-right tabular-nums">{l.http_status ?? "—"}</TableCell>
                            <TableCell className="text-right tabular-nums">
                              {l.items_found} / {l.new_items} / {l.changed_items}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">{l.duration_ms} ms</TableCell>
                          </TableRow>
                          {l.error ? (
                            <TableRow>
                              <TableCell colSpan={5} className="pt-0 text-xs text-rose-400">
                                {l.error}
                              </TableCell>
                            </TableRow>
                          ) : null}
                        </React.Fragment>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </TabsContent>
              <TabsContent value="items">
                {items.error ? <ErrorBanner error={items.error} onRetry={() => items.mutate()} /> : null}
                {!items.data ? (
                  <Skeleton className="h-32 w-full" />
                ) : items.data.length === 0 ? (
                  <p className="py-6 text-center text-sm text-muted-foreground">No items collected from this source yet.</p>
                ) : (
                  <ul className="divide-y">
                    {items.data.map((it) => (
                      <li key={it.id} className="py-2.5 text-sm">
                        <div className="flex items-start justify-between gap-3">
                          <a href={it.url} target="_blank" rel="noopener noreferrer" className="font-medium hover:text-primary hover:underline">
                            {it.title}
                          </a>
                          {it.duplicate_of_id ? <Badge tone="orange">dup #{it.duplicate_of_id}</Badge> : null}
                        </div>
                        {it.snippet ? <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{it.snippet}</p> : null}
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {it.publisher ?? "—"} · published {fmtDate(it.published_at, "unknown")} ({humanize(it.date_source)}) · discovered {fmtDate(it.discovered_at)} · {humanize(it.item_type)}
                          {it.version > 1 ? ` · v${it.version}` : ""}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </TabsContent>
            </Tabs>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function AddSourceDialog({ companyId, open, onOpenChange, onAdded }: { companyId: number; open: boolean; onOpenChange: (o: boolean) => void; onAdded: () => void }) {
  const competitors = useApi<Competitor[]>(open ? paths.competitors(companyId) : null);
  const empty = { name: "", url: "", category: "market", source_type: "rss", description: "", reason: "", approve: true, competitor_id: "none" };
  const [f, setF] = React.useState(empty);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (f.name.trim().length < 2) errs.name = "Enter a name.";
    if (!/^https?:\/\/\S+\.\S+/.test(f.url.trim())) errs.url = "Enter a full http(s) URL.";
    if (!f.reason.trim()) errs.reason = "Explain why this source matters — it's shown on the source card.";
    setErrors(errs);
    setFormError(null);
    if (Object.keys(errs).length) return;
    setSaving(true);
    try {
      const s = await api.addSource(companyId, {
        name: f.name.trim(),
        url: f.url.trim(),
        category: f.category,
        source_type: f.source_type,
        description: f.description.trim() || null,
        reason: f.reason.trim(),
        approve: f.approve,
        competitor_id: f.competitor_id !== "none" ? Number(f.competitor_id) : null,
      });
      toast.success(`Source added: ${s.name}`, { description: `Expected relevance ${pct(s.expected_relevance)} · ${s.update_frequency} updates` });
      setF(empty);
      onOpenChange(false);
      onAdded();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const d = err.detail as { name?: string; duplicate_of_id?: number } | null;
        setFormError(`This URL is already in your stack${d?.name ? ` as “${d.name}” (#${d.duplicate_of_id})` : ""}.`);
        setErrors({ url: "Duplicate source" });
      } else if (err instanceof ApiError && err.status === 422) {
        const fe = fieldErrors(err);
        if (Object.keys(fe).length) setErrors(fe);
        setFormError(typeof err.detail === "string" ? `Blocked: ${err.detail}` : "Please fix the highlighted fields.");
      } else {
        setFormError(errorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Add a source</DialogTitle>
          <DialogDescription>We check robots.txt and probe the source to estimate relevance and update frequency before adding it.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4" noValidate>
          {formError ? (
            <div role="alert" className="flex items-start gap-2 rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-600 dark:text-rose-300">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {formError}
            </div>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="as-name">Name</Label>
              <Input id="as-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} aria-invalid={!!errors.name} />
              {errors.name ? <p className="text-xs text-rose-500">{errors.name}</p> : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="as-url">URL</Label>
              <Input id="as-url" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://…/feed.xml" aria-invalid={!!errors.url} />
              {errors.url ? <p className="text-xs text-rose-500">{errors.url}</p> : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="as-cat">Category</Label>
              <Select value={f.category} onValueChange={(v) => setF({ ...f, category: v })}>
                <SelectTrigger id="as-cat">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["customers", "competitors", "market", "internal"].map((c) => (
                    <SelectItem key={c} value={c}>
                      {humanize(c)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="as-type">Source type</Label>
              <Select value={f.source_type} onValueChange={(v) => setF({ ...f, source_type: v })}>
                <SelectTrigger id="as-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SOURCE_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {humanize(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {f.category === "competitors" ? (
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="as-comp">Competitor (optional)</Label>
                <Select value={f.competitor_id} onValueChange={(v) => setF({ ...f, competitor_id: v })}>
                  <SelectTrigger id="as-comp">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not linked</SelectItem>
                    {(competitors.data ?? [])
                      .filter((c) => c.status !== "rejected")
                      .map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>
                          {c.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-reason">Reason for inclusion</Label>
            <Textarea id="as-reason" rows={2} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} aria-invalid={!!errors.reason} />
            {errors.reason ? <p className="text-xs text-rose-500">{errors.reason}</p> : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-desc">Description (optional)</Label>
            <Textarea id="as-desc" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} maxLength={1000} />
          </div>
          <div className="flex items-center gap-2">
            <Switch id="as-approve" checked={f.approve} onCheckedChange={(v) => setF({ ...f, approve: v })} />
            <Label htmlFor="as-approve">Approve and start monitoring immediately</Label>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              {saving ? "Probing source…" : "Add source"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SourcesInner() {
  const id = useCompanyId();
  const search = useSearchParams();
  const jobs = useJobRunner(id);
  const [category, setCategory] = React.useState("all");
  const [approval, setApproval] = React.useState(search.get("approval") ?? "all");
  const [health, setHealth] = React.useState(search.get("health") ?? "all");
  const [q, setQ] = React.useState("");
  const [qDebounced, setQDebounced] = React.useState("");
  const [selected, setSelected] = React.useState<Set<number>>(new Set());
  const [detail, setDetail] = React.useState<Source | null>(null);
  const [addOpen, setAddOpen] = React.useState(false);
  const [bulkBusy, setBulkBusy] = React.useState<string | null>(null);

  React.useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const key = paths.sources(id, {
    category: category === "all" ? undefined : category,
    approval_status: approval === "all" ? undefined : approval,
    health_status: health === "all" ? undefined : health,
    q: qDebounced || undefined,
  });
  const { data, error, isLoading, mutate } = useApi<Source[]>(key);
  const dups = useApi<Duplicate[]>(paths.duplicates(id));
  const sources = React.useMemo(() => data ?? [], [data]);
  const recommendedPending = sources.filter((s) => s.approval_status === "pending" && s.recommended && !s.duplicate_of_id).length;

  React.useEffect(() => {
    setSelected((prev) => new Set(Array.from(prev).filter((x) => sources.some((s) => s.id === x))));
  }, [sources]);

  const refresh = async () => {
    await Promise.all([mutate(), dups.mutate()]);
  };

  const patch = async (s: Source, body: { approval_status?: string; monitoring_status?: string }, msg: string) => {
    try {
      await api.updateSource(id, s.id, body);
      toast.success(msg);
      await refresh();
    } catch (e) {
      toast.error("Could not update source", { description: errorMessage(e) });
    }
  };

  const remove = async (s: Source) => {
    try {
      await api.removeSource(id, s.id);
      toast.success(`Removed ${s.name}`, { description: "Crawl history and evidence are kept for audit." });
      await refresh();
    } catch (e) {
      toast.error("Could not remove source", { description: errorMessage(e) });
    }
  };

  const bulk = async (action: string) => {
    setBulkBusy(action);
    try {
      const ids = action === "approve_recommended" ? [] : Array.from(selected);
      const r = await api.bulkSources(id, action, ids);
      toast.success(`${humanize(action)}: ${r.updated} source${r.updated === 1 ? "" : "s"} updated`);
      setSelected(new Set());
      await refresh();
    } catch (e) {
      toast.error("Bulk action failed", { description: errorMessage(e) });
    } finally {
      setBulkBusy(null);
    }
  };

  const allChecked = sources.length > 0 && selected.size === sources.length;
  const someChecked = selected.size > 0 && !allChecked;
  const filtersActive = category !== "all" || approval !== "all" || health !== "all" || !!qDebounced;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Source Manager"
        title="Sources"
        description="Approve, pause or remove sources; inspect crawl history and collected items; add your own."
        actions={
          <>
            <Button variant="outline" loading={jobs.isRunning("discover")} onClick={() => jobs.run("discover", "Source discovery", () => api.discoverSources(id))}>
              <Wand2 /> Discover more sources
            </Button>
            <Button variant="outline" loading={bulkBusy === "approve_recommended"} onClick={() => bulk("approve_recommended")}>
              <Sparkles /> Approve all recommended{recommendedPending ? ` (${recommendedPending})` : ""}
            </Button>
            <Button onClick={() => setAddOpen(true)}>
              <Plus /> Add source
            </Button>
          </>
        }
      />

      <Card className="p-3">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
            <Input className="pl-9" placeholder="Search name or URL…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search sources" />
          </div>
          <div className="grid grid-cols-3 gap-2 md:flex">
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="md:w-40" aria-label="Category">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {["customers", "competitors", "market", "internal"].map((c) => (
                  <SelectItem key={c} value={c}>
                    {humanize(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={approval} onValueChange={setApproval}>
              <SelectTrigger className="md:w-40" aria-label="Approval">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any approval</SelectItem>
                {["pending", "approved", "rejected"].map((c) => (
                  <SelectItem key={c} value={c}>
                    {humanize(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={health} onValueChange={setHealth}>
              <SelectTrigger className="md:w-36" aria-label="Health">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any health</SelectItem>
                {HEALTH.map((c) => (
                  <SelectItem key={c} value={c}>
                    {humanize(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        {selected.size > 0 ? (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md bg-primary/10 p-2 text-sm" role="region" aria-label="Bulk actions">
            <span className="px-1 font-medium">{selected.size} selected</span>
            <Button size="xs" variant="success" loading={bulkBusy === "approve"} onClick={() => bulk("approve")}>
              <Check className="h-3 w-3" /> Approve
            </Button>
            <Button size="xs" variant="outline" loading={bulkBusy === "reject"} onClick={() => bulk("reject")}>
              <X className="h-3 w-3" /> Reject
            </Button>
            <Button size="xs" variant="outline" loading={bulkBusy === "pause"} onClick={() => bulk("pause")}>
              <Pause className="h-3 w-3" /> Pause
            </Button>
            <Button size="xs" variant="outline" loading={bulkBusy === "resume"} onClick={() => bulk("resume")}>
              <Play className="h-3 w-3" /> Resume
            </Button>
            <Confirm title={`Remove ${selected.size} sources?`} description="They stop being monitored. Crawl history and evidence are kept." confirmLabel="Remove" onConfirm={() => bulk("remove")}>
              <Button size="xs" variant="destructive" loading={bulkBusy === "remove"}>
                <Trash2 className="h-3 w-3" /> Remove
              </Button>
            </Confirm>
            <Button size="xs" variant="ghost" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
          </div>
        ) : null}
      </Card>

      {error ? <ErrorBanner error={error} onRetry={() => mutate()} /> : null}

      <Card>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : sources.length === 0 ? (
          <EmptyState
            className="m-4"
            icon={Radar}
            title={filtersActive ? "No sources match these filters" : "No sources yet"}
            description={filtersActive ? "Try clearing a filter." : "Sources are proposed during setup. Discover more automatically or add one yourself."}
            action={
              filtersActive ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    setCategory("all");
                    setApproval("all");
                    setHealth("all");
                    setQ("");
                  }}
                >
                  Clear filters
                </Button>
              ) : (
                <>
                  <Button onClick={() => setAddOpen(true)}>
                    <Plus /> Add source
                  </Button>
                  <Button variant="outline" loading={jobs.isRunning("discover")} onClick={() => jobs.run("discover", "Source discovery", () => api.discoverSources(id))}>
                    <Wand2 /> Discover sources
                  </Button>
                </>
              )
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={allChecked ? true : someChecked ? "indeterminate" : false}
                    onCheckedChange={(v) => setSelected(v ? new Set(sources.map((s) => s.id)) : new Set())}
                    aria-label="Select all sources"
                  />
                </TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Approval</TableHead>
                <TableHead>Health</TableHead>
                <TableHead className="text-right">Credibility</TableHead>
                <TableHead className="text-right">Relevance</TableHead>
                <TableHead>Last checked</TableHead>
                <TableHead className="w-10">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((s) => (
                <TableRow key={s.id} data-state={selected.has(s.id) ? "selected" : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={selected.has(s.id)}
                      onCheckedChange={(v) =>
                        setSelected((prev) => {
                          const n = new Set(prev);
                          if (v) n.add(s.id);
                          else n.delete(s.id);
                          return n;
                        })
                      }
                      aria-label={`Select ${s.name}`}
                    />
                  </TableCell>
                  <TableCell className="max-w-[340px]">
                    <button className="block max-w-full truncate text-left font-medium hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => setDetail(s)}>
                      {s.name}
                    </button>
                    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <span>{humanize(s.source_type)}</span>
                      {s.recommended && s.approval_status === "pending" ? <Badge tone="violet">Recommended</Badge> : null}
                      {s.duplicate_of_id ? <Badge tone="orange">Duplicate</Badge> : null}
                      {s.approval_status === "approved" && s.monitoring_status === "paused" ? <MonitoringBadge status="paused" /> : null}
                    </div>
                  </TableCell>
                  <TableCell>
                    <CategoryBadge category={s.category} />
                  </TableCell>
                  <TableCell>
                    <ApprovalBadge status={s.approval_status} />
                  </TableCell>
                  <TableCell>
                    <HealthBadge status={s.health_status} />
                    {s.consecutive_failures > 0 ? <span className="ml-1 text-[10px] text-rose-400">×{s.consecutive_failures}</span> : null}
                  </TableCell>
                  <TableCell className="text-right tabular-nums" title={s.credibility_label}>
                    {pct(s.credibility)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{pct(s.expected_relevance)}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{fmtRelative(s.last_checked_at, "Never")}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${s.name}`}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setDetail(s)}>
                          <Eye /> View details
                        </DropdownMenuItem>
                        {s.approval_status !== "approved" ? (
                          <DropdownMenuItem onSelect={() => patch(s, { approval_status: "approved" }, `Approved ${s.name}`)}>
                            <Check /> Approve
                          </DropdownMenuItem>
                        ) : null}
                        {s.approval_status !== "rejected" ? (
                          <DropdownMenuItem onSelect={() => patch(s, { approval_status: "rejected" }, `Rejected ${s.name}`)}>
                            <X /> Reject
                          </DropdownMenuItem>
                        ) : null}
                        {s.monitoring_status === "active" ? (
                          <DropdownMenuItem onSelect={() => patch(s, { monitoring_status: "paused" }, `Paused ${s.name}`)}>
                            <Pause /> Pause monitoring
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onSelect={() => patch(s, { monitoring_status: "active" }, `Resumed ${s.name}`)}>
                            <Play /> Resume monitoring
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuItem onSelect={() => jobs.run(`check-${s.id}`, `Check ${s.name}`, () => api.checkSource(id, s.id))}>
                          <RefreshCw /> Check now
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem destructive onSelect={() => remove(s)}>
                          <Trash2 /> Remove
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Copy className="h-4 w-4 text-orange-400" aria-hidden /> Duplicate sources
          </CardTitle>
          <CardDescription>Sources whose feeds substantially overlap another source. Remove the duplicate to save crawl budget.</CardDescription>
        </CardHeader>
        <CardContent>
          {dups.error ? <ErrorBanner error={dups.error} onRetry={() => dups.mutate()} /> : null}
          {!dups.data ? (
            <Skeleton className="h-10 w-full" />
          ) : dups.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">No duplicates detected.</p>
          ) : (
            <ul className="divide-y">
              {dups.data.map((d) => (
                <li key={d.source_id} className="flex flex-col gap-2 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate">
                      <span className="font-medium">{d.name}</span> <span className="text-muted-foreground">duplicates</span> <span className="font-medium">{d.duplicate_of_name}</span>
                    </p>
                    <EvidenceLink url={d.url} companyId={id} className="text-xs" />
                  </div>
                  <Confirm title={`Remove “${d.name}”?`} description={`It duplicates “${d.duplicate_of_name}”, which stays.`} confirmLabel="Remove duplicate" onConfirm={() => remove({ id: d.source_id, name: d.name } as Source)}>
                    <Button size="sm" variant="outline">
                      <Trash2 /> Remove duplicate
                    </Button>
                  </Confirm>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <SourceDetails companyId={id} source={detail} open={!!detail} onOpenChange={(o) => !o && setDetail(null)} />
      <AddSourceDialog companyId={id} open={addOpen} onOpenChange={setAddOpen} onAdded={refresh} />
    </div>
  );
}

export default function SourcesPage() {
  return (
    <React.Suspense fallback={null}>
      <SourcesInner />
    </React.Suspense>
  );
}
