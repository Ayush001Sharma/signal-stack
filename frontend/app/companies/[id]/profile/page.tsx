"use client";

import * as React from "react";
import { toast } from "sonner";
import { ChevronDown, Edit3, ExternalLink, Plus, RefreshCw, Save, Trash2, X, FileSearch, History, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Confirm } from "@/components/shared/confirm";
import { FactStatusBadge } from "@/components/shared/badges";
import { EvidenceLink } from "@/components/shared/links";
import { EmptyState, ErrorBanner, KeyValue, ListSkeleton, PageHeader } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, ApiError, errorMessage, fieldErrors, paths } from "@/lib/api";
import { FACT_STATUSES, type Company, type ContextChange, type Fact, type FactStatus } from "@/lib/types";
import { fmtDateTime, humanize, pct } from "@/lib/utils";

const FIELD_LABEL: Record<string, string> = {
  summary: "Summary",
  industry: "Industry",
  business_context: "Business context",
  positioning: "Positioning",
  products: "Products & services",
  customer_segments: "Customer segments",
  geographies: "Geographies",
  business_model: "Business model",
  revenue_streams: "Revenue streams",
  developments: "Public developments",
  contact: "Contact",
};
const FIELD_ORDER = ["summary", "industry", "business_context", "positioning", "products", "customer_segments", "geographies", "business_model", "revenue_streams", "developments", "contact"];

const STATUS_LABEL: Record<FactStatus, string> = {
  verified: "Verified",
  unverified: "Unverified",
  assumption: "AI / rule assumption",
  needs_confirmation: "Needs confirmation",
};

function Chips({ items, empty = "Not found" }: { items?: string[] | null; empty?: string }) {
  if (!items || items.length === 0) return <span className="text-sm text-muted-foreground">{empty}</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((x) => (
        <Badge key={x} tone="outline" className="text-xs text-foreground/80">
          {x}
        </Badge>
      ))}
    </div>
  );
}

function FactRow({ fact, companyId, onChange }: { fact: Fact; companyId: number; onChange: () => void }) {
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState(fact.value);
  const [status, setStatus] = React.useState<string>(fact.status);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (!editing) {
      setValue(fact.value);
      setStatus(fact.status);
    }
  }, [fact, editing]);

  const save = async () => {
    if (!value.trim()) {
      toast.error("Value cannot be empty");
      return;
    }
    setSaving(true);
    try {
      const body: { value?: string; status?: FactStatus } = {};
      if (value.trim() !== fact.value) body.value = value.trim();
      if (status !== fact.status) body.status = status as FactStatus;
      if (Object.keys(body).length) await api.updateFact(companyId, fact.id, body);
      toast.success("Fact updated");
      setEditing(false);
      onChange();
    } catch (e) {
      toast.error("Could not update fact", { description: errorMessage(e) });
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    try {
      await api.deleteFact(companyId, fact.id);
      toast.success("Fact deleted");
      onChange();
    } catch (e) {
      toast.error("Could not delete fact", { description: errorMessage(e) });
    }
  };

  return (
    <li className="rounded-lg border bg-background/30 p-3">
      {editing ? (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor={`fv-${fact.id}`}>Value</Label>
            <Textarea id={`fv-${fact.id}`} rows={2} value={value} onChange={(e) => setValue(e.target.value)} maxLength={2000} />
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1.5">
              <Label htmlFor={`fs-${fact.id}`}>Status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger id={`fs-${fact.id}`} className="w-56">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FACT_STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {STATUS_LABEL[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="ml-auto flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
                <X /> Cancel
              </Button>
              <Button size="sm" loading={saving} onClick={save}>
                <Save /> Save
              </Button>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">Editing a value marks its origin as “user”.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-sm">{fact.value}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
              <FactStatusBadge status={fact.status} />
              <Badge tone="outline">origin: {fact.origin}</Badge>
              {fact.source_url ? (
                <EvidenceLink url={fact.source_url} companyId={companyId} className="text-[11px]" />
              ) : null}
              <span>updated {fmtDateTime(fact.updated_at)}</span>
            </div>
            {fact.evidence ? <p className="mt-1.5 border-l-2 border-border pl-2 text-xs text-muted-foreground">{fact.evidence}</p> : null}
          </div>
          <div className="flex shrink-0 gap-1">
            <Button variant="ghost" size="icon-sm" onClick={() => setEditing(true)} aria-label={`Edit fact: ${fact.value.slice(0, 40)}`}>
              <Edit3 />
            </Button>
            <Confirm title="Delete this fact?" description={`“${fact.value.slice(0, 120)}” will be removed from the profile.`} confirmLabel="Delete" onConfirm={remove}>
              <Button variant="ghost" size="icon-sm" aria-label={`Delete fact: ${fact.value.slice(0, 40)}`}>
                <Trash2 />
              </Button>
            </Confirm>
          </div>
        </div>
      )}
    </li>
  );
}

function AddFactDialog({ companyId, fields, onAdded }: { companyId: number; fields: string[]; onAdded: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [f, setF] = React.useState({ field: "products", customField: "", value: "", status: "verified" as FactStatus, source_url: "", evidence: "" });
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);
  const allFields = Array.from(new Set([...FIELD_ORDER, ...fields]));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const field = f.field === "__custom" ? f.customField.trim().toLowerCase().replace(/\s+/g, "_") : f.field;
    const errs: Record<string, string> = {};
    if (!field) errs.field = "Choose or enter a field.";
    if (!f.value.trim()) errs.value = "Enter a value.";
    if (f.source_url && !/^https?:\/\//.test(f.source_url)) errs.source_url = "Use a full http(s) URL.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    try {
      await api.addFact(companyId, { field, value: f.value.trim(), status: f.status, source_url: f.source_url || null, evidence: f.evidence || null });
      toast.success("Fact added");
      setOpen(false);
      setF({ field: "products", customField: "", value: "", status: "verified", source_url: "", evidence: "" });
      onAdded();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setErrors(fieldErrors(err));
      toast.error("Could not add fact", { description: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus /> Add fact
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a profile fact</DialogTitle>
          <DialogDescription>Facts you add are stored with origin “user”. Mark them verified only if you can stand behind them.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="af-field">Field</Label>
              <Select value={f.field} onValueChange={(v) => setF({ ...f, field: v })}>
                <SelectTrigger id="af-field">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {allFields.map((x) => (
                    <SelectItem key={x} value={x}>
                      {FIELD_LABEL[x] ?? humanize(x)}
                    </SelectItem>
                  ))}
                  <SelectItem value="__custom">Other (custom)…</SelectItem>
                </SelectContent>
              </Select>
              {f.field === "__custom" ? (
                <Input aria-label="Custom field name" placeholder="e.g. pricing" value={f.customField} onChange={(e) => setF({ ...f, customField: e.target.value })} />
              ) : null}
              {errors.field ? <p className="text-xs text-rose-500">{errors.field}</p> : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="af-status">Status</Label>
              <Select value={f.status} onValueChange={(v) => setF({ ...f, status: v as FactStatus })}>
                <SelectTrigger id="af-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FACT_STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {STATUS_LABEL[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="af-value">Value</Label>
            <Textarea id="af-value" rows={2} value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} aria-invalid={!!errors.value} />
            {errors.value ? <p className="text-xs text-rose-500">{errors.value}</p> : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="af-url">Source URL (optional)</Label>
            <Input id="af-url" value={f.source_url} onChange={(e) => setF({ ...f, source_url: e.target.value })} placeholder="https://…" aria-invalid={!!errors.source_url} />
            {errors.source_url ? <p className="text-xs text-rose-500">{errors.source_url}</p> : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="af-ev">Evidence (optional)</Label>
            <Textarea id="af-ev" rows={2} value={f.evidence} onChange={(e) => setF({ ...f, evidence: e.target.value })} maxLength={1500} />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Add fact
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ContextChangeCard({ cc }: { cc: ContextChange }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Context change · {fmtDateTime(cc.created_at)}</CardTitle>
          <Badge tone="slate">#{cc.id}</Badge>
        </div>
        <CardDescription className="text-sm">{cc.summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Before</p>
            <p className="text-sm">{cc.old_context.industry ?? "—"}</p>
            <p className="line-clamp-3 text-xs text-muted-foreground">{cc.old_context.business_context ?? "No business context"}</p>
          </div>
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">After</p>
            <p className="text-sm">{cc.new_context.industry ?? "—"}</p>
            <p className="line-clamp-3 text-xs text-muted-foreground">{cc.new_context.business_context ?? "No business context"}</p>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-1.5 text-xs font-medium">Added keywords</p>
            <div className="flex flex-wrap gap-1">
              {cc.added_keywords.length ? cc.added_keywords.map((k) => <Badge key={k} tone="emerald">+ {k}</Badge>) : <span className="text-xs text-muted-foreground">None</span>}
            </div>
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium">Removed keywords</p>
            <div className="flex flex-wrap gap-1">
              {cc.removed_keywords.length ? cc.removed_keywords.map((k) => <Badge key={k} tone="rose">− {k}</Badge>) : <span className="text-xs text-muted-foreground">None</span>}
            </div>
          </div>
        </div>
        {cc.flagged_sources.length ? (
          <div>
            <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-500" aria-hidden /> Flagged sources ({cc.flagged_sources.length})
            </p>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {cc.flagged_sources.map((f) => (
                <li key={f.source_id}>
                  <span className="font-medium text-foreground">{f.name}</span> — {f.why}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {cc.new_source_ids.length ? <p className="text-xs text-muted-foreground">{cc.new_source_ids.length} new sources proposed (see Source Manager → pending).</p> : null}
        {cc.relevance_changes.length ? (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="group -ml-2">
                Relevance changes ({cc.relevance_changes.length}) <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead className="text-right">Before</TableHead>
                    <TableHead className="text-right">After</TableHead>
                    <TableHead className="text-right">Δ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cc.relevance_changes.map((r) => (
                    <TableRow key={r.source_id}>
                      <TableCell className="max-w-[280px] truncate">{r.name}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(r.before)}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(r.after)}</TableCell>
                      <TableCell className={`text-right tabular-nums ${r.delta > 0.03 ? "text-emerald-500" : r.delta < -0.03 ? "text-rose-500" : "text-muted-foreground"}`}>
                        {r.delta > 0 ? "+" : ""}
                        {(r.delta * 100).toFixed(1)} pts
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ContextSection({ company }: { company: Company }) {
  const jobs = useJobRunner(company.id);
  const changes = useApi<ContextChange[]>(paths.contextChanges(company.id));
  const [industry, setIndustry] = React.useState(company.industry ?? "");
  const [ctx, setCtx] = React.useState(company.business_context ?? "");
  const [err, setErr] = React.useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ctx.trim()) {
      setErr("Describe the new business context.");
      return;
    }
    setErr(null);
    await jobs.run("context", "Business context reassessment", () => api.changeContext(company.id, { industry: industry.trim() || null, business_context: ctx.trim() }));
  };

  return (
    <section aria-labelledby="ctx-h" className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle id="ctx-h">Change business context</CardTitle>
          <CardDescription>
            Pivoting or refocusing? We’ll recompute keywords, re-score every source’s relevance, flag sources that no longer fit and propose new ones.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="ctx-ind">Industry (optional)</Label>
              <Input id="ctx-ind" value={industry} onChange={(e) => setIndustry(e.target.value)} maxLength={200} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ctx-text">New business context</Label>
              <Textarea id="ctx-text" rows={4} value={ctx} onChange={(e) => setCtx(e.target.value)} aria-invalid={!!err} maxLength={4000} placeholder="e.g. We are moving from B2C student counselling to B2B partnerships with universities in the UK and Ireland." />
              {err ? <p className="text-xs text-rose-500">{err}</p> : null}
            </div>
            <div className="flex justify-end">
              <Button type="submit" loading={jobs.isRunning("context")}>
                <RefreshCw /> Reassess sources for new context
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <History className="h-4 w-4 text-primary" aria-hidden /> Past context changes
      </h3>
      {changes.error ? <ErrorBanner error={changes.error} onRetry={() => changes.mutate()} /> : null}
      {changes.data && changes.data.length === 0 ? <p className="text-sm text-muted-foreground">No context changes yet.</p> : null}
      {(changes.data ?? []).map((cc) => (
        <ContextChangeCard key={cc.id} cc={cc} />
      ))}
    </section>
  );
}

export default function ProfilePage() {
  const id = useCompanyId();
  const company = useApi<Company>(paths.company(id));
  const facts = useApi<Fact[]>(paths.facts(id));
  const jobs = useJobRunner(id);
  const [statusFilter, setStatusFilter] = React.useState("all");

  const c = company.data;
  const p = c?.profile ?? {};
  const rs = c?.research_summary ?? {};
  const grouped = React.useMemo(() => {
    const g: Record<string, Fact[]> = {};
    for (const f of facts.data ?? []) {
      if (statusFilter !== "all" && f.status !== statusFilter) continue;
      (g[f.field] ??= []).push(f);
    }
    const keys = Object.keys(g).sort((a, b) => {
      const ia = FIELD_ORDER.indexOf(a);
      const ib = FIELD_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b);
    });
    return keys.map((k) => [k, g[k]] as const);
  }, [facts.data, statusFilter]);
  const counts = React.useMemo(() => {
    const out: Record<string, number> = {};
    for (const f of facts.data ?? []) out[f.status] = (out[f.status] ?? 0) + 1;
    return out;
  }, [facts.data]);
  const errors = (rs.errors ?? []) as unknown[];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Company Intelligence Profile"
        title={c?.name ?? "Profile"}
        description="What we know about the company — every fact carries its status, origin and evidence."
        actions={
          <Button variant="outline" loading={jobs.isRunning("research")} onClick={() => jobs.run("research", "Website research", () => api.rerunResearch(id))}>
            <FileSearch /> Re-run research
          </Button>
        }
      />
      {company.error ? <ErrorBanner error={company.error} onRetry={() => company.mutate()} /> : null}
      {!c ? (
        <ListSkeleton rows={2} />
      ) : (
        <>
          {c.research_error ? (
            <div role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
              <span className="font-medium">Research problem: </span>
              {c.research_error}
            </div>
          ) : null}
          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="glow-card xl:col-span-2">
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-base">Overview</CardTitle>
                  <Badge tone="slate">profile v{c.profile_version}</Badge>
                  <Badge tone={c.status === "error" ? "rose" : "emerald"}>{humanize(c.status)}</Badge>
                </div>
                {p.one_liner ? (
                  <p className="mt-2 text-[15px] leading-relaxed">{p.one_liner}</p>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">No summary yet — research may still be running.</p>
                )}
                {p.one_liner ? <p className="text-[11px] text-violet-400">One-liner is an assumption (AI or rule-generated), not a verified fact.</p> : null}
              </CardHeader>
              <CardContent>
                <dl className="grid gap-5 sm:grid-cols-2">
                  <KeyValue label="Industry">
                    {c.industry ?? p.industry ?? "—"}
                    {p.industry_confidence !== undefined && !c.industry ? <span className="ml-1 text-xs text-muted-foreground">(confidence {pct(p.industry_confidence)})</span> : null}
                  </KeyValue>
                  <KeyValue label="Website">
                    <EvidenceLink url={c.website} companyId={id}>
                      {c.domain}
                    </EvidenceLink>
                  </KeyValue>
                  <div className="sm:col-span-2">
                    <KeyValue label="Positioning">{p.positioning ?? <span className="text-muted-foreground">Not found</span>}</KeyValue>
                  </div>
                  <KeyValue label="Products & services">
                    <Chips items={p.products} />
                  </KeyValue>
                  <KeyValue label="Customer segments">
                    <Chips items={p.customer_segments} />
                  </KeyValue>
                  <KeyValue label="Geographies">
                    <Chips items={p.geographies} />
                  </KeyValue>
                  <KeyValue label="Business model">
                    <Chips items={p.business_model} />
                  </KeyValue>
                  <div className="sm:col-span-2">
                    <KeyValue label={`Monitoring keywords (${c.keywords.length})`}>
                      <Chips items={c.keywords} empty="No keywords yet" />
                    </KeyValue>
                  </div>
                  {c.business_context ? (
                    <div className="sm:col-span-2">
                      <KeyValue label="Business context">{c.business_context}</KeyValue>
                    </div>
                  ) : null}
                </dl>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Research summary</CardTitle>
                <CardDescription>How this profile was built.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <dl className="grid grid-cols-2 gap-4">
                  <KeyValue label="Pages crawled">{rs.pages_crawled?.length ?? 0}</KeyValue>
                  <KeyValue label="Errors">{errors.length}</KeyValue>
                  <KeyValue label="Feeds found">{rs.feeds_found?.length ?? 0}</KeyValue>
                  <KeyValue label="Developments">{rs.developments_found ?? 0}</KeyValue>
                  <KeyValue label="LLM">{rs.method?.llm?.available ? rs.method.llm.model ?? "available" : "not used"}</KeyValue>
                  <KeyValue label="Embeddings">{rs.method?.embeddings ?? "—"}</KeyValue>
                </dl>
                {rs.pages_crawled?.length ? (
                  <Collapsible>
                    <CollapsibleTrigger asChild>
                      <Button variant="ghost" size="sm" className="group -ml-2">
                        Crawled pages <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" />
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
                        {rs.pages_crawled.map((u) => (
                          <li key={u} className="truncate">
                            <a href={u} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                              {u}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </CollapsibleContent>
                  </Collapsible>
                ) : null}
                {errors.length ? (
                  <div>
                    <p className="mb-1 text-xs font-medium">Errors</p>
                    <ul className="max-h-32 space-y-1 overflow-y-auto text-xs text-rose-400">
                      {errors.map((e, i) => (
                        <li key={i} className="break-words">
                          {typeof e === "string" ? e : JSON.stringify(e)}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <div>
                  <p className="mb-1 text-xs font-medium">Name collisions excluded</p>
                  {rs.name_collisions_excluded?.length ? (
                    <>
                      <p className="mb-1.5 text-[11px] text-muted-foreground">News that matched the name but not the company (low semantic similarity) was excluded.</p>
                      <ul className="space-y-1 text-xs">
                        {rs.name_collisions_excluded.map((n) => (
                          <li key={n.url} className="flex items-center justify-between gap-2">
                            <a href={n.url} target="_blank" rel="noopener noreferrer" className="truncate text-muted-foreground hover:text-primary hover:underline">
                              {n.title}
                            </a>
                            <span className="shrink-0 tabular-nums text-muted-foreground">{pct(n.similarity)}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <p className="text-xs text-muted-foreground">None</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}

      <section aria-labelledby="facts-h">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 id="facts-h" className="text-sm font-semibold">
              Profile facts
            </h2>
            <p className="text-xs text-muted-foreground">
              {Object.entries(counts)
                .map(([k, v]) => `${v} ${STATUS_LABEL[k as FactStatus]?.toLowerCase() ?? k}`)
                .join(" · ") || "No facts yet"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-48" aria-label="Filter facts by status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {FACT_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <AddFactDialog companyId={id} fields={grouped.map(([k]) => k)} onAdded={() => facts.mutate()} />
          </div>
        </div>
        {facts.error ? <ErrorBanner error={facts.error} onRetry={() => facts.mutate()} /> : null}
        {facts.isLoading ? (
          <ListSkeleton rows={3} />
        ) : grouped.length === 0 ? (
          <EmptyState
            title={statusFilter === "all" ? "No facts yet" : "No facts with this status"}
            description={statusFilter === "all" ? "Facts are extracted when website research completes. You can also add facts yourself." : "Try another status filter."}
            action={statusFilter === "all" ? <AddFactDialog companyId={id} fields={[]} onAdded={() => facts.mutate()} /> : <Button variant="outline" onClick={() => setStatusFilter("all")}>Show all</Button>}
          />
        ) : (
          <div className="gap-4 lg:columns-2 [&>*]:mb-4 [&>*]:break-inside-avoid">
            {grouped.map(([field, list]) => (
              <Card key={field}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between">
                    {FIELD_LABEL[field] ?? humanize(field)}
                    <Badge tone="slate">{list.length}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2">
                    {list.map((f) => (
                      <FactRow key={f.id} fact={f} companyId={id} onChange={() => facts.mutate()} />
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      {c ? <ContextSection company={c} /> : null}
      <p className="text-center text-[11px] text-muted-foreground">
        <ExternalLink className="mr-1 inline h-3 w-3" aria-hidden />
        Source links open the original page in a new tab.
      </p>
    </div>
  );
}
