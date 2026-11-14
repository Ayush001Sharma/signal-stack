import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function toDate(v: string | number | Date | null | undefined): Date | null {
  if (v === null || v === undefined || v === "") return null;
  const d = v instanceof Date ? v : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "13 Nov 2026" */
export function fmtDate(v: string | Date | null | undefined, fallback = "—"): string {
  const d = toDate(v);
  if (!d) return fallback;
  // Date-only ISO strings (YYYY-MM-DD) are rendered in UTC to avoid off-by-one shifts.
  const dateOnly = typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: dateOnly ? "UTC" : undefined });
}

/** "13 Nov 2026, 14:05" in the viewer's local time zone. */
export function fmtDateTime(v: string | Date | null | undefined, fallback = "—"): string {
  const d = toDate(v);
  if (!d) return fallback;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Relative time like "3h ago" / "in 2d". */
export function fmtRelative(v: string | Date | null | undefined, fallback = "—"): string {
  const d = toDate(v);
  if (!d) return fallback;
  const diff = d.getTime() - Date.now();
  const abs = Math.abs(diff);
  const units: Array<[number, Intl.RelativeTimeFormatUnit]> = [
    [60_000, "second"],
    [3_600_000, "minute"],
    [86_400_000, "hour"],
    [604_800_000, "day"],
    [2_629_800_000, "week"],
    [31_557_600_000, "month"],
    [Infinity, "year"],
  ];
  const div: Record<string, number> = { second: 1000, minute: 60_000, hour: 3_600_000, day: 86_400_000, week: 604_800_000, month: 2_629_800_000, year: 31_557_600_000 };
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto", style: "short" });
  for (const [limit, unit] of units) {
    if (abs < limit) return rtf.format(Math.round(diff / div[unit]), unit);
  }
  return fmtDate(d);
}

export function fmtDuration(start: string | null | undefined, end: string | null | undefined): string {
  const a = toDate(start);
  const b = toDate(end);
  if (!a || !b) return "—";
  const ms = b.getTime() - a.getTime();
  if (ms < 1000) return `${ms} ms`;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/** 0–1 → "72%" */
export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function score100(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Math.round(v).toString();
}

export function humanize(s: string | null | undefined): string {
  if (!s) return "—";
  const t = s.replace(/[_-]+/g, " ").trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function hostOf(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function isHttp(url: string | null | undefined): url is string {
  return !!url && /^https?:\/\//i.test(url);
}

/** Translate an APScheduler trigger string to plain English. */
export function describeTrigger(trigger: string): string {
  const interval = trigger.match(/^interval\[(.+)\]$/);
  if (interval) {
    const body = interval[1];
    const days = body.match(/(\d+) day/);
    const hms = body.match(/(\d+):(\d{2}):(\d{2})/);
    const parts: string[] = [];
    if (days) parts.push(`${days[1]} day${days[1] === "1" ? "" : "s"}`);
    if (hms) {
      const h = Number(hms[1]);
      const m = Number(hms[2]);
      if (h) parts.push(`${h} hour${h === 1 ? "" : "s"}`);
      if (m) parts.push(`${m} min`);
    }
    return `Every ${parts.join(" ") || body}`;
  }
  const cron = trigger.match(/^cron\[(.+)\]$/);
  if (cron) {
    const kv: Record<string, string> = {};
    for (const m of Array.from(cron[1].matchAll(/(\w+)='([^']*)'/g))) kv[m[1]] = m[2];
    const time = kv.hour !== undefined ? `${kv.hour.padStart(2, "0")}:${(kv.minute ?? "0").padStart(2, "0")}` : "";
    const dayNames: Record<string, string> = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };
    if (kv.day_of_week) return `Every ${dayNames[kv.day_of_week] ?? kv.day_of_week} at ${time}`;
    if (kv.day) return `Monthly on day ${kv.day} at ${time}`;
    return `Cron ${cron[1]}`;
  }
  return trigger;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}
