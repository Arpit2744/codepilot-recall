"use client";

import type { SyncJob, SyncStatusResponse } from "@codepilot/contracts";
import { Button } from "@/components/ui/button";

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-amber-500/15 text-amber-300",
  running: "bg-sky-500/15 text-sky-300",
  succeeded: "bg-emerald-500/15 text-emerald-300",
  failed: "bg-rose-500/15 text-rose-300",
  cancelled: "bg-slate-500/15 text-slate-300",
};

function StatusChip({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        STATUS_STYLES[status] ?? STATUS_STYLES.cancelled
      }`}
    >
      {status}
    </span>
  );
}

function jobHint(job: SyncJob | undefined): string {
  if (!job) return "No sync jobs yet.";
  if (job.status === "pending") return "Waiting for a worker to pick up the job…";
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
      className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">
          {status ? `@${status.account.handle}` : "Sync status"}
        </h2>
        {job ? <StatusChip status={job.status} /> : null}
      </div>

      {status ? (
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-slate-500">Submissions</dt>
            <dd className="font-medium">{status.totals.submissions}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Solved problems</dt>
            <dd className="font-medium">{status.totals.solved_problems}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Last synced</dt>
            <dd className="font-medium">
              {status.account.last_synced_at
                ? status.account.last_synced_at.slice(0, 16).replace("T", " ") + " UTC"
                : "never"}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Job type</dt>
            <dd className="font-medium">{job?.job_type ?? "—"}</dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-slate-400">Loading sync status…</p>
      )}

      <p aria-live="polite" className="text-sm text-slate-400">
        {jobHint(job)}
      </p>

      {failed && job?.error_summary ? (
        <p role="alert" className="rounded-lg border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
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
