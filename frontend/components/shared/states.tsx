"use client";

import * as React from "react";
import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions, eyebrow }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow ? <div className="mb-1 text-xs font-medium uppercase tracking-wider text-primary">{eyebrow}</div> : null}
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {description ? <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="no-print flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-xl border border-dashed bg-muted/20 px-6 py-10 text-center", className)}>
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="text-sm font-semibold">{title}</h3>
      {description ? <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}

export function ErrorBanner({ error, onRetry, title = "Something went wrong" }: { error: unknown; onRetry?: () => void; title?: string }) {
  return (
    <div role="alert" className="mb-4 flex flex-col gap-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" aria-hidden />
        <div>
          <p className="font-medium text-rose-600 dark:text-rose-300">{title}</p>
          <p className="text-rose-700/80 dark:text-rose-200/80">{errorMessage(error)}</p>
        </div>
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw /> Retry
        </Button>
      ) : null}
    </div>
  );
}

export function CardsSkeleton({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-4", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <Card key={i} className="p-5">
          <Skeleton className="mb-3 h-3 w-24" />
          <Skeleton className="h-7 w-16" />
        </Card>
      ))}
    </div>
  );
}

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Card key={i} className="p-5">
          <Skeleton className="mb-3 h-4 w-2/3" />
          <Skeleton className="mb-2 h-3 w-full" />
          <Skeleton className="h-3 w-1/2" />
        </Card>
      ))}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  tone?: "default" | "rose" | "emerald" | "amber" | "violet";
  className?: string;
}) {
  const toneCls: Record<string, string> = {
    default: "text-primary bg-primary/10",
    rose: "text-rose-500 bg-rose-500/10",
    emerald: "text-emerald-500 bg-emerald-500/10",
    amber: "text-amber-500 bg-amber-500/10",
    violet: "text-violet-500 bg-violet-500/10",
  };
  return (
    <Card className={cn("relative overflow-hidden p-4", className)}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
          {hint ? <p className="mt-1 truncate text-[11px] text-muted-foreground">{hint}</p> : null}
        </div>
        {Icon ? (
          <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", toneCls[tone])}>
            <Icon className="h-4 w-4" />
          </div>
        ) : null}
      </div>
    </Card>
  );
}

/** Horizontal 0–1 meter with label and % value. */
export function Meter({ label, value, color = "bg-primary", hint }: { label: string; value: number | null | undefined; color?: string; hint?: string }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  return (
    <div className="min-w-0" title={hint}>
      <div className="mb-1 flex items-center justify-between gap-2 text-[11px]">
        <span className="truncate text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{value === null || value === undefined ? "—" : `${Math.round(v * 100)}%`}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)}>
        <div className={cn("h-full rounded-full", color)} style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  );
}

export function SectionTitle({ children, actions, id }: { children: React.ReactNode; actions?: React.ReactNode; id?: string }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <h2 id={id} className="text-sm font-semibold tracking-tight">
        {children}
      </h2>
      {actions}
    </div>
  );
}

export function KeyValue({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words text-sm">{children}</dd>
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;
  return (
    <nav className="mt-4 flex items-center justify-between gap-2 text-sm" aria-label="Pagination">
      <span className="text-muted-foreground">
        Page {page} of {pages} · {total} total
      </span>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </Button>
      </div>
    </nav>
  );
}
