"use client";

import * as React from "react";
import { Area, AreaChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CATEGORY_COLOR, CATEGORY_LABEL, HEALTH_COLOR } from "@/components/shared/badges";
import { humanize } from "@/lib/utils";

const tooltipStyle: React.CSSProperties = {
  background: "hsl(var(--popover))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 8,
  fontSize: 12,
  color: "hsl(var(--popover-foreground))",
};

export function HealthDonut({ health }: { health: Record<string, number> }) {
  const data = Object.entries(health)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ name: humanize(k), key: k, value: v }));
  const total = data.reduce((a, b) => a + b.value, 0);
  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row">
      <div className="relative h-44 w-44 shrink-0" role="img" aria-label={`Source health: ${data.map((d) => `${d.value} ${d.name}`).join(", ")}`}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={52} outerRadius={78} paddingAngle={2} stroke="none" isAnimationActive={false}>
              {data.map((d) => (
                <Cell key={d.key} fill={HEALTH_COLOR[d.key] ?? "#64748b"} />
              ))}
            </Pie>
            <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: "hsl(var(--popover-foreground))" }} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold tabular-nums">{total}</span>
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">monitored</span>
        </div>
      </div>
      <ul className="w-full space-y-1.5 text-sm">
        {data.map((d) => (
          <li key={d.key} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: HEALTH_COLOR[d.key] ?? "#64748b" }} aria-hidden />
              {d.name}
            </span>
            <span className="tabular-nums text-muted-foreground">
              {d.value} <span className="text-[11px]">({Math.round((d.value / Math.max(1, total)) * 100)}%)</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SignalTrendChart({ data }: { data: Array<{ date: string; customers: number; competitors: number; market: number; internal: number }> }) {
  const cats = ["customers", "competitors", "market", "internal"] as const;
  const rows = data.map((d) => ({ ...d, label: new Date(`${d.date}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" }) }));
  return (
    <div className="h-64 w-full" role="img" aria-label="Meaningful signals per day by category over the last 30 days">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <defs>
            {cats.map((c) => (
              <linearGradient key={c} id={`g-${c}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={CATEGORY_COLOR[c]} stopOpacity={0.45} />
                <stop offset="100%" stopColor={CATEGORY_COLOR[c]} stopOpacity={0.03} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="hsl(var(--chart-grid))" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} minTickGap={16} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} />
          <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: "hsl(var(--muted-foreground))" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" iconSize={8} />
          {cats.map((c) => (
            <Area key={c} type="monotone" dataKey={c} name={CATEGORY_LABEL[c]} stackId="1" stroke={CATEGORY_COLOR[c]} strokeWidth={1.5} fill={`url(#g-${c})`} isAnimationActive={false} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
