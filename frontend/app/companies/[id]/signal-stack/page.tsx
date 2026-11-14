"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Building2, Check, FileText, Globe2, Layers, Upload, Users, Swords, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorBanner, ListSkeleton, PageHeader } from "@/components/shared/states";
import { SourceCard } from "@/components/source-card";
import { useApi } from "@/hooks/use-api";
import { useCompanyId } from "@/hooks/use-company-id";
import { api, errorMessage, paths } from "@/lib/api";
import type { Category, SignalStack, Source } from "@/lib/types";
import { fmtDate, humanize } from "@/lib/utils";

const COLS: Array<{ key: Category; label: string; icon: React.ComponentType<{ className?: string }>; desc: string }> = [
  { key: "customers", label: "Customers", icon: Users, desc: "Where your customers talk: communities, reviews, Q&A." },
  { key: "competitors", label: "Competitors", icon: Swords, desc: "Competitor sites, feeds, changelogs and news." },
  { key: "market", label: "Market", icon: Globe2, desc: "Industry news, regulation and macro signals." },
  { key: "internal", label: "Internal", icon: Building2, desc: "Your own uploaded CRM, support and sales data." },
];

export default function SignalStackPage() {
  const id = useCompanyId();
  const { data, error, isLoading, mutate } = useApi<SignalStack>(paths.signalStack(id));
  const [busy, setBusy] = React.useState<number | null>(null);

  const setApproval = async (s: Source, approval_status: "approved" | "rejected") => {
    setBusy(s.id);
    try {
      await api.updateSource(id, s.id, { approval_status });
      toast.success(`${s.name} ${approval_status}`);
      await mutate();
    } catch (e) {
      toast.error("Could not update source", { description: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Signal Stack"
        title="Your monitored intelligence sources"
        description="Every source shows why it was included, how credible it is and how relevant we expect it to be. Approve the ones you trust."
        actions={
          <Button variant="outline" asChild>
            <Link href={`/companies/${id}/sources`}>
              <Layers /> Open Source Manager
            </Link>
          </Button>
        }
      />
      {error ? <ErrorBanner error={error} onRetry={() => mutate()} /> : null}
      {isLoading || !data ? (
        <ListSkeleton rows={3} />
      ) : (
        <Tabs defaultValue="customers">
          <TabsList className="h-auto flex-wrap">
            {COLS.map((c) => (
              <TabsTrigger key={c.key} value={c.key}>
                <c.icon className="h-3.5 w-3.5" /> {c.label}
                <span className="ml-1 rounded bg-background/60 px-1.5 text-[10px] tabular-nums">
                  {c.key === "internal" ? data.internal?.documents?.length ?? 0 : data[c.key]?.sources.length ?? 0}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
          {COLS.map((c) => {
            const col = data[c.key];
            return (
              <TabsContent key={c.key} value={c.key}>
                <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  <span>{c.desc}</span>
                  {c.key !== "internal" ? (
                    <>
                      <Badge tone="emerald">{col?.approved ?? 0} approved</Badge>
                      <Badge tone="amber">{col?.pending ?? 0} pending</Badge>
                    </>
                  ) : null}
                </div>
                {c.key === "internal" ? (
                  <div className="space-y-3">
                    {col?.documents?.length ? (
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {col.documents.map((d) => (
                          <Card key={d.id} className="flex items-start gap-3 p-4">
                            <FileText className="mt-0.5 h-5 w-5 text-emerald-500" aria-hidden />
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium">{d.filename}</p>
                              <p className="text-xs text-muted-foreground">
                                {d.records} records · uploaded {fmtDate(d.uploaded_at)}
                              </p>
                            </div>
                            <Badge tone={d.status === "processed" ? "emerald" : d.status === "error" ? "rose" : "amber"}>{humanize(d.status)}</Badge>
                          </Card>
                        ))}
                      </div>
                    ) : (
                      <EmptyState
                        icon={Upload}
                        title="No internal documents yet"
                        description="Upload CRM exports, call notes, support logs or survey results. We extract themes with quotes so the brief includes your own data."
                        action={
                          <Button asChild>
                            <Link href={`/companies/${id}/uploads`}>
                              <Upload /> Upload documents
                            </Link>
                          </Button>
                        }
                      />
                    )}
                    {col?.documents?.length ? (
                      <Button variant="outline" asChild>
                        <Link href={`/companies/${id}/uploads`}>
                          <Upload /> Manage uploads
                        </Link>
                      </Button>
                    ) : null}
                  </div>
                ) : col?.sources.length ? (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {col.sources.map((s) => (
                      <SourceCard
                        key={s.id}
                        source={s}
                        companyId={id}
                        actions={
                          s.approval_status === "pending" ? (
                            <>
                              <Button size="xs" variant="success" loading={busy === s.id} onClick={() => setApproval(s, "approved")}>
                                <Check className="h-3 w-3" /> Approve
                              </Button>
                              <Button size="xs" variant="ghost" disabled={busy === s.id} onClick={() => setApproval(s, "rejected")}>
                                <X className="h-3 w-3" /> Reject
                              </Button>
                            </>
                          ) : null
                        }
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={c.icon}
                    title={`No ${c.label.toLowerCase()} sources yet`}
                    description="Sources are proposed during setup and audits. You can discover more or add one manually in the Source Manager."
                    action={
                      <Button asChild>
                        <Link href={`/companies/${id}/sources`}>Open Source Manager</Link>
                      </Button>
                    }
                  />
                )}
              </TabsContent>
            );
          })}
        </Tabs>
      )}
    </div>
  );
}
