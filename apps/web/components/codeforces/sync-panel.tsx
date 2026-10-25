"use client";

import type { BadgeTone } from "@/components/ui/status-badge";
import { StatusBadge } from "@/components/ui/status-badge";
import type { SyncJob, SyncStatusResponse } from "@codepilot/contracts";
import { Button } from "@/components/ui/button";

const statusTones: Record<string, BadgeTone> = {
  pending: "warning",
  running: "info",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
};

function StatusChip({ status }: { status: string }) {
  return <StatusBadge tone={statusTones[status] ?? "neutral"}>{status}</StatusBadge>;
}

function jobHint(job: SyncJob | undefined): string {
  if (!job) return "No sync jobs yet.";
  if (job.status === "pending") {
    return "Queued — the periodic worker runs syncs about every 4 hours, or use Sync now to request a run.";
  }
  if (job.status === "running") {
    const seen = job.progress?.submissions_seen ?? 0;
    return seen > 0 ? `Importing — ${seen} submissions seen so far.` : "Importing…";
  }
  if (job.status === "succeeded") {
    const added = job.progress?.new_submissions ?? 0;
    return `Imported ${added} new submission${added === 1 ? "" : "s"}.`;
  }
  if (job.status === "failed") {
    return job.error_summary ?? "Sync failed.";
  }
  return "Sync was skipped because another sync was already running.";
}

export function SyncPanel({
  status,
  onSyncNow,
  syncing,
}: {
  status: SyncStatusResponse | null;
  onSyncNow: () => void;
  syncing: boolean;
}) {
  const job = status?.latest_jobs?.[0];
  const active = job?.status === "pending" || job?.status === "running";
  const failed = job?.status === "failed";

  return (
    <section
      aria-label="Synchronization status"
      className="panel flex flex-col gap-4 p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-baseline gap-2 text-base font-semibold tracking-tight">
          <span className="text-slate-500">@</span>
          <span className="font-mono text-slate-100">
            {status ? status.account.handle : "Sync status"}
          </span>
        </h2>
        {job ? <StatusChip status={job.status} /> : null}
      </div>

      {status ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="micro-label">Submissions</dt>
            <dd className="mt-0.5 font-medium text-slate-100">{status.totals.submissions}</dd>
          </div>
          <div>
            <dt className="micro-label">Solved problems</dt>
            <dd className="mt-0.5 font-medium text-slate-100">{status.totals.solved_problems}</dd>
          </div>
          <div>
            <dt className="micro-label">Last synced</dt>
            <dd className="mt-0.5 font-medium text-slate-300">
              {status.account.last_synced_at
                ? status.account.last_synced_at.slice(0, 16).replace("T", " ") + " UTC"
                : "never"}
            </dd>
          </div>
          <div>
            <dt className="micro-label">Job type</dt>
            <dd className="mt-0.5 font-medium text-slate-300">{job?.job_type ?? "—"}</dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-slate-400">Loading sync status…</p>
      )}

      <p aria-live="polite" className="text-sm leading-relaxed text-slate-400">
        {jobHint(job)}
      </p>

      {failed && job?.error_summary ? (
        <p
          role="alert"
          className="rounded-lg border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300"
        >
          {job.error_summary}
        </p>
      ) : null}

      <div>
        <Button variant="secondary" onClick={onSyncNow} disabled={syncing || active}>
          {active ? "Sync in progress…" : "Sync now"}
        </Button>
      </div>
    </section>
  );
}
