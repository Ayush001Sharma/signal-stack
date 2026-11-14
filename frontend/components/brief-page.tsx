"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileText, History, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { BriefExportButtons, BriefView } from "@/components/brief-view";
import { EmptyState, ErrorBanner, ListSkeleton, PageHeader } from "@/components/shared/states";
import { useApi } from "@/hooks/use-api";
import { useJobRunner } from "@/hooks/use-job-runner";
import { api, ApiError, paths } from "@/lib/api";
import type { Brief, BriefSummary, Page } from "@/lib/types";

function GenerateBriefButton({ companyId, onGenerated }: { companyId: number; onGenerated: (briefId?: number) => void }) {
  const jobs = useJobRunner(companyId);
  const [lookback, setLookback] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const valid = lookback === "" || (/^\d+$/.test(lookback) && Number(lookback) >= 1 && Number(lookback) <= 120);
  const go = async () => {
    if (!valid) return;
    setOpen(false);
    const job = await jobs.run("brief", "Monday Brief", () => api.generateBrief(companyId, lookback ? { lookback_days: Number(lookback) } : {}));
    if (job && job.status !== "failed") {
      const bid = typeof job.details?.brief_id === "number" ? (job.details.brief_id as number) : undefined;
      onGenerated(bid);
    }
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button loading={jobs.isRunning("brief")}>
          <Sparkles /> Generate new brief
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="lookback">Lookback window (days, optional)</Label>
          <Input id="lookback" inputMode="numeric" placeholder="Default from schedule settings" value={lookback} onChange={(e) => setLookback(e.target.value.trim())} aria-invalid={!valid} />
          {!valid ? <p className="text-xs text-rose-500">Enter a number between 1 and 120.</p> : null}
          <p className="text-[11px] text-muted-foreground">Runs a fresh crawl first, then builds the brief from stored, evidence-backed signals. This can take a few minutes.</p>
        </div>
        <Button className="w-full" onClick={go} disabled={!valid}>
          <Sparkles /> Generate
        </Button>
      </PopoverContent>
    </Popover>
  );
}

/** Shared page for /brief (latest) and /briefs/[briefId]. */
export function BriefPage({ companyId, briefId }: { companyId: number; briefId?: number }) {
  const router = useRouter();
  // For "latest", look up the newest brief id via the history list (avoids a 404 when none exist yet).
  const latest = useApi<Page<BriefSummary>>(briefId ? null : paths.briefs(companyId, { page: 1, page_size: 1 }));
  const resolvedId = briefId ?? latest.data?.items[0]?.id;
  const brief = useApi<Brief>(resolvedId ? paths.brief(companyId, resolvedId) : null, { shouldRetryOnError: (e: unknown) => !(e instanceof ApiError && e.status === 404) });
  const data = brief.data;
  const error = brief.error ?? latest.error;
  const isLoading = brief.isLoading || latest.isLoading;
  const mutate = () => Promise.all([latest.mutate(), brief.mutate()]);
  const notFound = (error instanceof ApiError && error.status === 404) || (!briefId && latest.data !== undefined && latest.data.items.length === 0);

  const onGenerated = (bid?: number) => {
    if (bid) router.push(`/companies/${companyId}/briefs/${bid}`);
    else void mutate();
  };

  const actions = (
    <>
      {data ? <BriefExportButtons brief={data} companyId={companyId} /> : null}
      <Button variant="ghost" size="sm" asChild>
        <Link href={`/companies/${companyId}/history`}>
          <History /> History
        </Link>
      </Button>
      <GenerateBriefButton companyId={companyId} onGenerated={onGenerated} />
    </>
  );

  return (
    <div>
      <PageHeader eyebrow="Monday Morning Brief" title={briefId ? `Brief #${briefId}` : "Latest brief"} description="Ten fixed sections. Every item cites its source; empty sections say so — nothing is invented." actions={actions} />
      {error && !notFound ? <ErrorBanner error={error} onRetry={() => mutate()} /> : null}
      {notFound ? (
        <EmptyState
          icon={FileText}
          title={briefId ? "Brief not found" : "No brief yet"}
          description={
            briefId
              ? "This brief doesn't exist for this company. Open the history to pick another."
              : "Generate your first Monday Morning Brief now, or wait for the scheduled weekly run (see Automation)."
          }
          action={briefId ? <Button asChild><Link href={`/companies/${companyId}/history`}>Open history</Link></Button> : <GenerateBriefButton companyId={companyId} onGenerated={onGenerated} />}
        />
      ) : isLoading || !data ? (
        error ? null : <ListSkeleton rows={4} />
      ) : (
        <BriefView brief={data} companyId={companyId} />
      )}
    </div>
  );
}
