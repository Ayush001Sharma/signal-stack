"use client";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ApprovalBadge, HealthBadge, MonitoringBadge } from "@/components/shared/badges";
import { EvidenceLink } from "@/components/shared/links";
import { Meter } from "@/components/shared/states";
import type { Source } from "@/lib/types";
import { fmtDate, humanize } from "@/lib/utils";

export function SourceCard({ source, companyId, actions }: { source: Source; companyId: number; actions?: React.ReactNode }) {
  const s = source;
  return (
    <Card className="flex h-full flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="line-clamp-2 text-sm font-semibold leading-snug">{s.name}</h3>
          <EvidenceLink url={s.url} companyId={companyId} className="mt-0.5 max-w-full text-xs" />
        </div>
        <Badge tone="outline" className="shrink-0">
          {humanize(s.source_type)}
        </Badge>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        <ApprovalBadge status={s.approval_status} />
        <HealthBadge status={s.health_status} />
        {s.approval_status === "approved" ? <MonitoringBadge status={s.monitoring_status} /> : null}
        {s.recommended && s.approval_status === "pending" ? <Badge tone="violet">Recommended</Badge> : null}
        {s.competitor_name ? <Badge tone="violet">{s.competitor_name}</Badge> : null}
        {s.duplicate_of_id ? <Badge tone="orange">Duplicate of #{s.duplicate_of_id}</Badge> : null}
      </div>
      {s.reason ? (
        <p className="mt-3 text-xs">
          <span className="font-medium">Why included: </span>
          <span className="text-muted-foreground">{s.reason}</span>
        </p>
      ) : null}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Meter label={`Credibility · ${s.credibility_label}`} value={s.credibility} color="bg-sky-500" hint={s.credibility_rationale ?? undefined} />
        <Meter label="Expected relevance" value={s.expected_relevance} color="bg-violet-500" hint={s.relevance_rationale ?? undefined} />
      </div>
      {s.relevance_rationale ? <p className="mt-2 text-[11px] text-muted-foreground">{s.relevance_rationale}</p> : null}
      {s.credibility_rationale ? <p className="mt-1 text-[11px] text-muted-foreground">Credibility: {s.credibility_rationale}</p> : null}
      <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <dt className="text-muted-foreground">Update frequency</dt>
          <dd>{humanize(s.update_frequency)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Last checked</dt>
          <dd>{fmtDate(s.last_checked_at, "Never")}</dd>
        </div>
      </dl>
      {s.sample_items?.length ? (
        <div className="mt-3 border-t pt-2">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">Sample items</p>
          <ul className="space-y-1">
            {s.sample_items.slice(0, 3).map((it, i) => (
              <li key={i} className="flex items-start justify-between gap-2 text-xs">
                {it.url ? (
                  <a href={it.url} target="_blank" rel="noopener noreferrer" className="line-clamp-1 hover:text-primary hover:underline">
                    {it.title}
                  </a>
                ) : (
                  <span className="line-clamp-1">{it.title}</span>
                )}
                {it.date ? <span className="shrink-0 text-muted-foreground">{fmtDate(it.date)}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {actions ? <div className="mt-auto flex flex-wrap gap-1.5 pt-3">{actions}</div> : null}
    </Card>
  );
}
