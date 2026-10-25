"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type {
  CompleteReviewResponse,
  ReviewDueItem,
  ReviewSessionResponse,
  ReviewUpcomingItem,
} from "@codepilot/contracts";

type QueueItem = ReviewDueItem | ReviewUpcomingItem;

const STATUS_STYLES: Record<string, string> = {
  overdue: "bg-amber-500/15 text-amber-300",
  due: "bg-emerald-500/15 text-emerald-300",
  upcoming: "bg-slate-500/15 text-slate-300",
};

const TIER_STYLES: Record<number, string> = {
  1: "bg-rose-500/20 text-rose-300",
  2: "bg-amber-500/20 text-amber-300",
};

const RISK_STYLES: Record<string, string> = {
  high: "bg-rose-500/15 text-rose-300",
  elevated: "bg-amber-500/15 text-amber-300",
  low: "bg-emerald-500/15 text-emerald-300",
};
import { Button } from "@/components/ui/button";
import { listDueReviews, startReview, completeReview, ApiError } from "@/lib/reviews";
import { bootstrapSession, type SessionState } from "@/lib/auth";

type SessionPageState =
  | { phase: "loading" }
  | { phase: "anon" }
  | { phase: "unreachable" }
  | { phase: "ready"; userId: string };

const OUTCOMES = [
  { key: "again", label: "Again", hint: "Forgot / could not recall the approach" },
  { key: "hard", label: "Hard", hint: "Solved with significant struggle or a small hint" },
  { key: "good", label: "Good", hint: "Solved independently with reasonable effort" },
  { key: "easy", label: "Easy", hint: "Solved independently, quickly, confidently" },
] as const;

type OutcomeKey = (typeof OUTCOMES)[number]["key"];

export default function ReviewPage() {
  const [devUser, setDevUser] = useState<SessionPageState>({ phase: "loading" });
  const [queueItems, setQueueItems] = useState<QueueItem[] | null>(null);
  const [queueMode, setQueueMode] = useState<"due" | "upcoming">("due");
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const [active, setActive] = useState<ReviewSessionResponse | null>(null);
  const [helpLevel, setHelpLevel] = useState<"none" | "hint" | "editorial">("none");
  const [submitting, setSubmitting] = useState<OutcomeKey | null>(null);
  const [result, setResult] = useState<CompleteReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  useEffect(() => {
    let cancelled = false;
    bootstrapSession().then((state: SessionState) => {
      if (cancelled) return;
      if (state.phase === "auth") {
        setDevUser({ phase: "ready", userId: state.user.id });
      } else {
        setDevUser({ phase: state.phase });
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshQueue = useCallback(async (mode: "due" | "upcoming") => {
    try {
      setQueueItems((await listDueReviews(mode)).items);
      return true;
    } catch {
      setQueueItems(null);
      return false;
    }
  }, []);

  // Deep link support: /review?problem=<id> starts a review for one
  // solved problem (the dashboard table links here). Read via
  // window.location so prerendering needs no Suspense boundary.
  useEffect(() => {
    if (devUser.phase !== "ready" || active || result) return;
    const problemId = new URLSearchParams(window.location.search).get("problem");
    if (problemId) {
      begin(problemId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [devUser]);

  useEffect(() => {
    if (devUser.phase !== "ready") return;
    const timer = setTimeout(() => refreshQueue(queueMode), 0);
    return () => clearTimeout(timer);
  }, [devUser, queueMode, refreshQueue]);

  async function begin(problemId: string) {
    setError(null);
    setConflict(false);
    setResult(null);
    setHelpLevel("none");
    try {
      setActive(await startReview({ problem_id: problemId }));
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "Could not start the review.");
    }
  }

  async function submit(sessionId: string, outcome: OutcomeKey) {
    setSubmitting(outcome);
    setError(null);
    setConflict(false);
    try {
      const response = await completeReview(sessionId, {
        outcome,
        independent: helpLevel === "none" ? true : false,
        help_level: helpLevel,
      });
      setResult(response);
      setActive(null);
      // Server-confirmed completion: refresh the queue immediately and
      // report honestly if the refresh itself fails.
      const refreshed = await refreshQueue("due");
      setQueueMode("due");
      setRefreshWarning(
        refreshed
          ? null
          : "The review was recorded, but the queue could not be refreshed — the list below may be stale. Reload to see the latest schedule.",
      );
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 409) {
        setConflict(true);
        setActive(null);
      } else {
        setError(exc instanceof ApiError ? exc.message : "Could not submit the review.");
      }
    } finally {
      setSubmitting(null);
    }
  }

  function resetFlow() {
    setActive(null);
    setResult(null);
    setError(null);
    setConflict(false);
    setRefreshWarning(null);
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <Link href="/dashboard" className="text-sm text-slate-400 hover:text-slate-200">
            ← Dashboard
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Review</h1>
        </div>
        <Link
          href="/dashboard"
          className="text-sm text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline"
        >
          Back to dashboard
        </Link>
      </header>

      {devUser.phase === "loading" ? (
        <p role="status" className="text-sm text-slate-400">
          Preparing local session…
        </p>
      ) : null}

      {devUser.phase === "anon" ? (
        <section className="flex flex-col items-start gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-6">
          <h2 className="text-lg font-semibold">Log in to review</h2>
          <p className="text-sm text-slate-400">
            Your review queue and memory schedule live in your account.
          </p>
          <a
            href="/login"
            className="inline-flex items-center justify-center rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400"
          >
            Log in
          </a>
        </section>
      ) : null}

      {devUser.phase === "unreachable" ? (
        <section role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-900/60 bg-rose-950/40 p-5">
          <p className="text-sm text-rose-200">
            Could not reach the API. The API service may be waking up —
            wait a few seconds and retry.
          </p>
          <div>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        </section>
      ) : null}

      {devUser.phase === "ready" ? (
        active ? (
          <section
            aria-label="Active review session"
            className="flex flex-col gap-5 rounded-xl border border-slate-800 bg-slate-900/50 p-6"
          >
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">
                Attempt this problem honestly, then rate your recall
              </p>
              <h2 className="mt-1 text-xl font-semibold">
                {active.problem.contest_id
                  ? `${active.problem.contest_id}${active.problem.problem_index} — ${active.problem.name}`
                  : active.problem.name}
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Rating {active.problem.rating ?? "—"} ·{" "}
                {active.problem.tags.slice(0, 4).join(" · ") || "no tags"}
              </p>
              {active.problem.url ? (
                <a
                  href={active.problem.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block text-sm text-indigo-300 underline-offset-2 hover:underline"
                >
                  Open problem on Codeforces ↗
                </a>
              ) : null}
            </div>

            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm text-slate-300">Help used</legend>
              <div className="flex flex-wrap gap-2">
                {(["none", "hint", "editorial"] as const).map((level) => (
                  <label
                    key={level}
                    className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm transition-colors has-[:checked]:border-indigo-400 has-[:checked]:bg-indigo-500/20 ${
                      helpLevel === level ? "border-indigo-400 bg-indigo-500/20" : "border-slate-700"
                    }`}
                  >
                    <input
                      type="radio"
                      name="help-level"
                      className="sr-only"
                      checked={helpLevel === level}
                      onChange={() => setHelpLevel(level)}
                    />
                    {level === "none" ? "None (independent)" : level === "hint" ? "A hint" : "Editorial / major help"}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-2 sm:grid-cols-2">
              {OUTCOMES.map((outcome) => (
                <Button
                  key={outcome.key}
                  variant={outcome.key === "good" ? "primary" : "secondary"}
                  disabled={submitting !== null}
                  onClick={() => submit(active.session.id, outcome.key)}
                >
                  {submitting === outcome.key ? "Submitting…" : outcome.label}
                  <span className="sr-only"> — {outcome.hint}</span>
                </Button>
              ))}
            </div>
            <p className="text-xs text-slate-500">
              Again: forgot or needed major help · Hard: heavy struggle or a small
              hint · Good: independent with effort · Easy: independent, fast,
              confident. Only “None (independent)” + Good/Easy marks the solve as
              independently verified.
            </p>
          </section>
        ) : result ? (
          <section
            aria-label="Review recorded"
            className="flex flex-col gap-4 rounded-xl border border-emerald-900/60 bg-emerald-950/30 p-6"
          >
            <h2 className="text-lg font-semibold text-emerald-200">Review recorded</h2>
            {refreshWarning ? (
              <p role="alert" className="rounded-lg border border-amber-900/60 bg-amber-950/30 p-3 text-sm text-amber-200">
                {refreshWarning}
              </p>
            ) : null}
            <p className="text-sm text-slate-300">
              You rated{" "}
              <strong>{result.session.outcome}</strong>
              {result.session.independent === false ? " (with help — not counted as independent recall)" : ""}.
            </p>
            <p className="text-sm text-slate-300">
              Next review scheduled for{" "}
              <strong>{result.memory.due_at.slice(0, 16).replace("T", " ")} UTC</strong>{" "}
              (model estimate — FSRS {result.memory.scheduler_version}).
            </p>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={resetFlow}>
                Back to queue
              </Button>
            </div>
          </section>
        ) : conflict ? (
          <section
            role="alert"
            className="flex flex-col gap-3 rounded-xl border border-amber-900/60 bg-amber-950/30 p-6"
          >
            <h2 className="text-lg font-semibold text-amber-200">Already completed</h2>
            <p className="text-sm text-slate-300">
              This session was already completed — the scheduler was not advanced
              twice.
            </p>
            <div>
              <Button variant="secondary" onClick={resetFlow}>
                Back to queue
              </Button>
            </div>
          </section>
        ) : (
          <section aria-label="Review queue" className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-semibold">
                {queueMode === "due" ? "Due for review" : "Upcoming reviews"}
              </h2>
              <div role="tablist" aria-label="Queue mode" className="flex gap-1 rounded-lg bg-slate-950/60 p-1">
                {(["due", "upcoming"] as const).map((m) => (
                  <button
                    key={m}
                    role="tab"
                    aria-selected={queueMode === m}
                    onClick={() => setQueueMode(m)}
                    className={`rounded-md px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-indigo-400 ${
                      queueMode === m ? "bg-indigo-500 text-white" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {m === "due" ? "Due" : "Upcoming"}
                  </button>
                ))}
              </div>
            </div>
            {queueItems === null ? (
              <p className="text-sm text-slate-400">
                Could not load the review queue. The API may be waking up — retry shortly.
              </p>
            ) : queueItems.length === 0 ? (
              <p className="text-sm text-slate-400">
                {queueMode === "due"
                  ? "Nothing due right now. Reviews you complete will schedule themselves here — a Codeforces acceptance alone never creates a review."
                  : "No upcoming reviews scheduled yet."}
              </p>
            ) : (
              <ul className="divide-y divide-slate-800">
                {queueItems.map((item) => (
                  <li key={item.problem.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STATUS_STYLES[item.status]}`}
                        >
                          {item.status === "overdue" ? "Overdue" : item.status === "due" ? "Due now" : "Upcoming"}
                        </span>
                        {item.priority_tier !== null && TIER_STYLES[item.priority_tier] ? (
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${TIER_STYLES[item.priority_tier]}`}
                          >
                            {item.priority_tier === 1 ? "Critical" : "High"} priority
                          </span>
                        ) : null}
                        <p className="truncate text-sm text-slate-100">
                          {item.problem.contest_id
                            ? `${item.problem.contest_id}${item.problem.problem_index} — ${item.problem.name}`
                            : item.problem.name}
                        </p>
                      </div>
                      <p className="mt-0.5 text-xs text-slate-400">{item.priority_reason}</p>
                      <p className="text-xs text-slate-500">
                        due {item.due_at.slice(0, 16).replace("T", " ")} UTC ·{" "}
                        {item.repetitions} review{item.repetitions === 1 ? "" : "s"}
                        {item.lapses > 0 ? ` · ${item.lapses} lapse${item.lapses === 1 ? "" : "s"}` : ""}
                        {item.retrievability !== null && item.risk ? (
                          <>
                            {" · "}
                            <span className={`rounded px-1 ${RISK_STYLES[item.risk]}`}>
                              estimated recall ≈ {Math.round(item.retrievability * 100)}% ({item.risk} risk)
                            </span>{" "}
                            — model estimate
                          </>
                        ) : item.status !== "upcoming" && item.retrievability === null ? (
                          " · recall estimate unavailable"
                        ) : null}
                      </p>
                    </div>
                    <Button onClick={() => begin(item.problem.id)}>
                      Start review
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            {error ? (
              <p role="alert" className="text-sm text-rose-300">
                {error}
              </p>
            ) : null}
            <p className="text-xs text-slate-600">
              New here? Reviews are created from problems you have solved — open a
              solved problem from the{" "}
              <Link href="/dashboard" className="underline hover:text-slate-400">
                dashboard
              </Link>{" "}
              and the first review initializes its memory.
            </p>
          </section>
        )
      ) : null}

    </main>
  );
}
