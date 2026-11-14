"use client";

import * as React from "react";
import { toast } from "sonner";
import { Check, Trash2 } from "lucide-react";
import { useSWRConfig } from "swr";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Confirm } from "@/components/shared/confirm";
import { useApi } from "@/hooks/use-api";
import { api, errorMessage, paths } from "@/lib/api";
import type { Audit, Source } from "@/lib/types";
import { fmtDate, fmtDateTime, humanize, pct } from "@/lib/utils";

function List({ title, items, empty = "None" }: { title: string; items: React.ReactNode[]; empty?: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between">
          {title} <Badge tone={items.length ? "amber" : "slate"}>{items.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>{items.length ? <ul className="space-y-1.5 text-sm">{items}</ul> : <p className="text-sm text-muted-foreground">{empty}</p>}</CardContent>
    </Card>
  );
}

export function AuditView({ audit, companyId }: { audit: Audit; companyId: number }) {
  const c = audit.content;
  const { mutate } = useSWRConfig();
  // Current source state, so we can tell which recommendations were already acted on.
  const sources = useApi<Source[]>(paths.sources(companyId, { include_removed: true }));
  const byId = new Map((sources.data ?? []).map((s) => [s.id, s]));
  const [busy, setBusy] = React.useState<string | null>(null);

  const refresh = () => mutate((k) => typeof k === "string" && k.startsWith(`/api/companies/${companyId}`));

  const approve = async (ids: number[]) => {
    setBusy(ids.length > 1 ? "approve-all" : `a-${ids[0]}`);
    try {
      for (const sid of ids) await api.updateSource(companyId, sid, { approval_status: "approved" });
      toast.success(`Approved ${ids.length} recommended source${ids.length > 1 ? "s" : ""}`);
      await refresh();
    } catch (e) {
      toast.error("Could not approve", { description: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };
  const remove = async (ids: number[]) => {
    setBusy(ids.length > 1 ? "remove-all" : `r-${ids[0]}`);
    try {
      for (const sid of ids) await api.removeSource(companyId, sid);
      toast.success(`Removed ${ids.length} source${ids.length > 1 ? "s" : ""}`);
      await refresh();
    } catch (e) {
      toast.error("Could not remove", { description: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };

  const addPending = c.recommend_add.filter((a) => byId.get(a.source_id)?.approval_status !== "approved");
  const removeOpen = Array.from(new Map(c.recommend_remove.filter((r) => byId.get(r.source_id)?.approval_status !== "removed").map((r) => [r.source_id, r])).values());

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Audit #{audit.id} · generated {fmtDateTime(audit.generated_at)} · trigger {humanize(audit.trigger)}
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Object.entries(c.summary).map(([k, v]) => (
          <Card key={k} className="p-3">
            <p className="text-[11px] text-muted-foreground">{humanize(k)}</p>
            <p className="text-xl font-semibold tabular-nums">{v}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle>Recommended additions</CardTitle>
                <CardDescription>New candidate sources the audit recommends approving.</CardDescription>
              </div>
              {addPending.length > 1 ? (
                <Button size="sm" variant="success" loading={busy === "approve-all"} onClick={() => approve(addPending.map((a) => a.source_id))}>
                  <Check /> Approve all ({addPending.length})
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardContent>
            {c.recommend_add.length ? (
              <ul className="divide-y">
                {c.recommend_add.map((a) => {
                  const st = byId.get(a.source_id)?.approval_status;
                  return (
                    <li key={a.source_id} className="flex items-start justify-between gap-3 py-2.5 text-sm">
                      <div className="min-w-0">
                        <p className="font-medium">{a.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {humanize(a.category)} · expected relevance {pct(a.expected_relevance)}
                          {a.why ? ` — ${a.why}` : ""}
                        </p>
                      </div>
                      {st === "approved" ? (
                        <Badge tone="emerald">Approved</Badge>
                      ) : st === "removed" || st === "rejected" ? (
                        <Badge tone="slate">{humanize(st)}</Badge>
                      ) : (
                        <Button size="xs" variant="success" loading={busy === `a-${a.source_id}`} onClick={() => approve([a.source_id])}>
                          <Check className="h-3 w-3" /> Approve
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No additions recommended.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle>Recommended removals</CardTitle>
                <CardDescription>Dead, duplicate or declining sources. Removal keeps history for audit.</CardDescription>
              </div>
              {removeOpen.length > 1 ? (
                <Confirm title={`Remove ${removeOpen.length} sources?`} description="They stop being monitored; crawl history and evidence are kept." confirmLabel="Remove all" onConfirm={() => remove(removeOpen.map((r) => r.source_id))}>
                  <Button size="sm" variant="destructive" loading={busy === "remove-all"}>
                    <Trash2 /> Remove all ({removeOpen.length})
                  </Button>
                </Confirm>
              ) : null}
            </div>
          </CardHeader>
          <CardContent>
            {c.recommend_remove.length ? (
              <ul className="divide-y">
                {c.recommend_remove.map((r, i) => {
                  const st = byId.get(r.source_id)?.approval_status;
                  return (
                    <li key={`${r.source_id}-${i}`} className="flex items-start justify-between gap-3 py-2.5 text-sm">
                      <div className="min-w-0">
                        <p className="font-medium">{r.name}</p>
                        <p className="text-xs text-muted-foreground">{r.why}</p>
                      </div>
                      {st === "removed" ? (
                        <Badge tone="slate">Removed</Badge>
                      ) : (
                        <Confirm title={`Remove “${r.name}”?`} description={r.why} confirmLabel="Remove" onConfirm={() => remove([r.source_id])}>
                          <Button size="xs" variant="outline" loading={busy === `r-${r.source_id}`}>
                            <Trash2 className="h-3 w-3" /> Remove
                          </Button>
                        </Confirm>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No removals recommended.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <List
          title="Dead / unavailable"
          items={c.dead.map((d) => (
            <li key={d.source_id}>
              <span className="font-medium">{d.name}</span> <span className="text-xs text-muted-foreground">— {d.error ?? d.status}</span>
            </li>
          ))}
        />
        <List
          title="Duplicates"
          items={c.duplicates.map((d) => (
            <li key={d.source_id}>
              {byId.get(d.source_id)?.name ?? `#${d.source_id}`} <span className="text-xs text-muted-foreground">duplicates {byId.get(d.duplicate_of)?.name ?? `#${d.duplicate_of}`}</span>
            </li>
          ))}
        />
        <List
          title="Inactive (45+ days)"
          items={c.inactive.map((d) => (
            <li key={d.source_id}>
              {d.name} <span className="text-xs text-muted-foreground">— latest item {d.latest_item ? fmtDate(d.latest_item) : "never"}</span>
            </li>
          ))}
        />
        <List
          title="Declining relevance"
          items={c.declining.map((d) => (
            <li key={d.source_id}>
              {d.name} <span className="text-xs text-muted-foreground">— {d.reason}</span>
            </li>
          ))}
        />
      </div>

      {c.availability.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Availability check</CardTitle>
            <CardDescription>HEAD request against every approved source during the audit.</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead className="text-right">HTTP</TableHead>
                  <TableHead>Error</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {c.availability.map((a) => (
                  <TableRow key={a.source_id}>
                    <TableCell>{a.name}</TableCell>
                    <TableCell>{a.ok ? <Badge tone="emerald">Available</Badge> : <Badge tone="rose">Unavailable</Badge>}</TableCell>
                    <TableCell className="text-right tabular-nums">{a.status ?? "—"}</TableCell>
                    <TableCell className="max-w-[360px] truncate text-xs text-muted-foreground">{a.error ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
