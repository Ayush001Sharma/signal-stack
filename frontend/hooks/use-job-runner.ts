"use client";

import { useCallback, useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { JobRun, JobStarted } from "@/lib/types";

const TERMINAL = (s: string) => s !== "queued" && s !== "running";

export interface RunOptions {
  /** Called with the finished job. */
  onDone?: (job: JobRun) => void;
  /** Revalidate SWR keys starting with this prefix when the job finishes (default: the company prefix). */
  revalidatePrefix?: string;
  /** Poll interval in ms. */
  intervalMs?: number;
}

/** Poll GET /api/jobs/{id} until the job leaves queued/running. */
export async function pollJob(jobId: number, intervalMs = 2000, signal?: { cancelled: boolean }, onTick?: (j: JobRun) => void): Promise<JobRun> {
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await api.getJob(jobId);
    onTick?.(job);
    if (TERMINAL(job.status)) return job;
    if (signal?.cancelled) return job;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

/**
 * Shared hook behind every "Run now" button: starts a job, shows a toast,
 * polls until it finishes, then revalidates data and reports the outcome.
 */
export function useJobRunner(companyId?: number) {
  const { mutate } = useSWRConfig();
  const [running, setRunning] = useState<Record<string, number | true>>({});

  const revalidate = useCallback(
    (prefix?: string) => {
      const p = prefix ?? (companyId ? `/api/companies/${companyId}` : "/api");
      return mutate((key) => typeof key === "string" && (key.startsWith(p) || key.startsWith("/api/jobs") || key.startsWith("/api/scheduler")));
    },
    [mutate, companyId],
  );

  const run = useCallback(
    async (key: string, label: string, start: () => Promise<JobStarted>, opts: RunOptions = {}) => {
      setRunning((r) => ({ ...r, [key]: true }));
      const tid = toast.loading(`${label}: starting…`);
      try {
        const started = await start();
        setRunning((r) => ({ ...r, [key]: started.job_run_id }));
        toast.loading(`${label}: job #${started.job_run_id} queued`, { id: tid, description: "You can keep working — we'll let you know when it finishes." });
        void revalidate(opts.revalidatePrefix);
        const job = await pollJob(started.job_run_id, opts.intervalMs ?? 2000, undefined, (j) => {
          if (j.status === "running") toast.loading(`${label}: running (job #${j.id})`, { id: tid, description: j.message ?? undefined });
        });
        if (job.status === "failed") {
          toast.error(`${label} failed`, { id: tid, description: job.message ?? job.error?.slice(0, 200) ?? undefined, duration: 10000 });
        } else if (job.status === "partial") {
          toast.warning(`${label} finished with warnings`, { id: tid, description: job.message ?? undefined, duration: 8000 });
        } else {
          toast.success(`${label} complete`, { id: tid, description: job.message ?? undefined, duration: 6000 });
        }
        await revalidate(opts.revalidatePrefix);
        opts.onDone?.(job);
        return job;
      } catch (err) {
        const already = err instanceof ApiError && err.status === 409;
        toast[already ? "warning" : "error"](already ? `${label}: already running` : `${label} failed to start`, {
          id: tid,
          description: errorMessage(err),
        });
        return null;
      } finally {
        setRunning((r) => {
          const n = { ...r };
          delete n[key];
          return n;
        });
      }
    },
    [revalidate],
  );

  return { run, running, isRunning: (key: string) => key in running, revalidate };
}
