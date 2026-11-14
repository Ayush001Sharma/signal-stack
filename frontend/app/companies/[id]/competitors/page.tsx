"use client";

import * as React from "react";
import { toast } from "sonner";
import { Check, ChevronDown, Plus, Swords, Undo2, Wand2, X, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CompetitorStatusBadge } from "@/components/shared/badges";
import { EvidenceLink } from "@/components/shared/links";
import { EmptyState, ErrorBanner, ListSkeleton, Meter, PageHeader } from "@/components/shared/states";
import { SignalMini } from "@/components/signal-card";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, ApiError, errorMessage, fieldErrors, paths } from "@/lib/api";
import type { Competitor, Page, Signal } from "@/lib/types";
import { fmtDate, humanize } from "@/lib/utils";

function CompetitorSignals({ companyId, competitorId }: { companyId: number; competitorId: number }) {
  const { data, error } = useApi<Page<Signal>>(paths.signals(companyId, { competitor_id: competitorId, category: "competitors", page_size: 5, sort: "date" }));
  if (error) return <p className="text-xs text-rose-400">Could not load signals.</p>;
  if (!data) return <p className="text-xs text-muted-foreground">Loading signals…</p>;
  if (!data.items.length) return <p className="text-xs text-muted-foreground">No meaningful signals for this competitor yet.</p>;
  return (
    <div className="divide-y">
      {data.items.map((s) => (
        <SignalMini key={s.id} signal={s} companyId={companyId} />
      ))}
      {data.total > 5 ? <p className="pt-2 text-[11px] text-muted-foreground">+{data.total - 5} more in the Intelligence Feed (filter by competitor).</p> : null}
    </div>
  );
}

function CompetitorCard({ c, companyId, onChange }: { c: Competitor; companyId: number; onChange: () => void }) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const setStatus = async (status: "confirmed" | "rejected" | "suggested") => {
    setBusy(status);
    try {
      await api.updateCompetitor(companyId, c.id, { status });
      toast.success(`${c.name}: ${status}`);
      onChange();
    } catch (e) {
      toast.error("Could not update competitor", { description: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };
  return (
    <Card className="flex flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-semibold">{c.name}</h3>
          {c.website ? (
            <EvidenceLink url={c.website} companyId={companyId} className="text-xs" />
          ) : (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Globe className="h-3 w-3" aria-hidden /> No website
            </span>
          )}
        </div>
        <CompetitorStatusBadge status={c.status} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        <Badge tone={c.kind === "direct" ? "violet" : "blue"}>{humanize(c.kind)}</Badge>
        <Badge tone="outline">via {humanize(c.discovery_method)}</Badge>
        {c.mention_count ? <Badge tone="outline">{c.mention_count} mentions</Badge> : null}
      </div>
      {c.description ? <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{c.description}</p> : null}
      <div className="mt-3">
        <Meter label="Confidence" value={c.confidence} color="bg-violet-500" />
      </div>
      {c.reason ? (
        <p className="mt-3 text-xs">
          <span className="font-medium">Why: </span>
          <span className="text-muted-foreground">{c.reason}</span>
        </p>
      ) : null}
      {c.evidence?.length ? (
        <Collapsible className="mt-2">
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="xs" className="group -ml-2">
              Evidence ({c.evidence.length}) <ChevronDown className="h-3 w-3 transition-transform group-data-[state=open]:rotate-180" />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-1 space-y-1.5 text-xs">
              {c.evidence.map((e, i) => (
                <li key={i}>
                  <EvidenceLink url={e.url} companyId={companyId}>
                    {e.title}
                  </EvidenceLink>
                  <span className="block text-[11px] text-muted-foreground">
                    {e.publisher ?? "—"} · {fmtDate(e.date, "undated")}
                    {e.query ? ` · query ${e.query}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
      <Collapsible className="mt-1">
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="xs" className="group -ml-2">
            Recent signals <ChevronDown className="h-3 w-3 transition-transform group-data-[state=open]:rotate-180" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-1">
          <CompetitorSignals companyId={companyId} competitorId={c.id} />
        </CollapsibleContent>
      </Collapsible>
      <div className="mt-auto flex flex-wrap gap-1.5 pt-3">
        {c.status !== "confirmed" ? (
          <Button size="xs" variant="success" loading={busy === "confirmed"} onClick={() => setStatus("confirmed")}>
            <Check className="h-3 w-3" /> Confirm
          </Button>
        ) : null}
        {c.status !== "rejected" ? (
          <Button size="xs" variant="outline" loading={busy === "rejected"} onClick={() => setStatus("rejected")}>
            <X className="h-3 w-3" /> Reject
          </Button>
        ) : null}
        {c.status !== "suggested" ? (
          <Button size="xs" variant="ghost" loading={busy === "suggested"} onClick={() => setStatus("suggested")}>
            <Undo2 className="h-3 w-3" /> Reset to suggested
          </Button>
        ) : null}
      </div>
    </Card>
  );
}

function AddCompetitorDialog({ companyId, onAdded }: { companyId: number; onAdded: () => void }) {
  const [open, setOpen] = React.useState(false);
  const empty = { name: "", website: "", description: "", kind: "direct" as "direct" | "substitute" };
  const [f, setF] = React.useState(empty);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!f.name.trim()) errs.name = "Enter the competitor's name.";
    if (f.website && !/^https?:\/\/\S+\.\S+/.test(f.website.trim())) errs.website = "Use a full http(s) URL.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    try {
      await api.addCompetitor(companyId, { name: f.name.trim(), website: f.website.trim() || null, description: f.description.trim() || null, kind: f.kind });
      toast.success(`${f.name} added as a confirmed competitor`);
      setF(empty);
      setOpen(false);
      onAdded();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setErrors({ name: "This competitor already exists." });
      else if (err instanceof ApiError && err.status === 422) setErrors(fieldErrors(err));
      else toast.error("Could not add competitor", { description: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> Add competitor
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a competitor</DialogTitle>
          <DialogDescription>Competitors you add are confirmed immediately and included in monitoring.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="ac-name">Name</Label>
            <Input id="ac-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} aria-invalid={!!errors.name} />
            {errors.name ? <p className="text-xs text-rose-500">{errors.name}</p> : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ac-web">Website (optional)</Label>
            <Input id="ac-web" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} placeholder="https://…" aria-invalid={!!errors.website} />
            {errors.website ? <p className="text-xs text-rose-500">{errors.website}</p> : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ac-kind">Kind</Label>
            <Select value={f.kind} onValueChange={(v) => setF({ ...f, kind: v as "direct" | "substitute" })}>
              <SelectTrigger id="ac-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="direct">Direct competitor</SelectItem>
                <SelectItem value="substitute">Substitute / alternative</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ac-desc">Description (optional)</Label>
            <Textarea id="ac-desc" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} maxLength={1000} />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Add competitor
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function CompetitorsPage() {
  const id = useCompanyId();
  const jobs = useJobRunner(id);
  const { data, error, isLoading, mutate } = useApi<Competitor[]>(paths.competitors(id));
  const [tab, setTab] = React.useState("active");
  const list = (data ?? []).filter((c) => (tab === "active" ? c.status !== "rejected" : tab === "all" ? true : c.status === tab));
  const count = (s: string) => (data ?? []).filter((c) => c.status === s).length;

  return (
    <div>
      <PageHeader
        eyebrow="Competitor intelligence"
        title="Competitors"
        description="Discovered from news co-mentions, your interview answers and manual additions — each with the evidence behind it."
        actions={
          <>
            <Button variant="outline" loading={jobs.isRunning("comp")} onClick={() => jobs.run("comp", "Competitor discovery", () => api.discoverCompetitors(id))}>
              <Wand2 /> Rediscover
            </Button>
            <AddCompetitorDialog companyId={id} onAdded={() => mutate()} />
          </>
        }
      />
      {error ? <ErrorBanner error={error} onRetry={() => mutate()} /> : null}
      <Tabs value={tab} onValueChange={setTab} className="mb-4">
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="active">Active ({(data ?? []).length - count("rejected")})</TabsTrigger>
          <TabsTrigger value="confirmed">Confirmed ({count("confirmed")})</TabsTrigger>
          <TabsTrigger value="suggested">Suggested ({count("suggested")})</TabsTrigger>
          <TabsTrigger value="rejected">Rejected ({count("rejected")})</TabsTrigger>
          <TabsTrigger value="all">All</TabsTrigger>
        </TabsList>
      </Tabs>
      {isLoading ? (
        <ListSkeleton rows={3} />
      ) : list.length === 0 ? (
        <EmptyState
          icon={Swords}
          title={data?.length ? "No competitors in this view" : "No competitors yet"}
          description={data?.length ? "Switch tabs to see others." : "Competitors are discovered during setup. Run discovery again or add the ones you know."}
          action={
            !data?.length ? (
              <>
                <Button variant="outline" loading={jobs.isRunning("comp")} onClick={() => jobs.run("comp", "Competitor discovery", () => api.discoverCompetitors(id))}>
                  <Wand2 /> Discover competitors
                </Button>
                <AddCompetitorDialog companyId={id} onAdded={() => mutate()} />
              </>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {list.map((c) => (
            <CompetitorCard key={c.id} c={c} companyId={id} onChange={() => mutate()} />
          ))}
        </div>
      )}
    </div>
  );
}
