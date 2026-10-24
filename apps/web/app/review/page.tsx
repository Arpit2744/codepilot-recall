"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type {
  CompleteReviewResponse,
  ReviewDueItem,
  ReviewSessionResponse,
} from "@codepilot/contracts";
import { Button } from "@/components/ui/button";
import { listDueReviews, startReview, completeReview, ApiError } from "@/lib/reviews";
import { ensureDevUser } from "@/lib/dev-user";

type DevUserState =
  | { phase: "loading" }
  | { phase: "error" }
  | { phase: "ready"; userId: string };

const OUTCOMES = [
  { key: "again", label: "Again", hint: "Forgot / could not recall the approach" },
  { key: "hard", label: "Hard", hint: "Solved with significant struggle or a small hint" },
  { key: "good", label: "Good", hint: "Solved independently with reasonable effort" },
  { key: "easy", label: "Easy", hint: "Solved independently, quickly, confidently" },
] as const;

type OutcomeKey = (typeof OUTCOMES)[number]["key"];

export default function ReviewPage() {
  const [devUser, setDevUser] = useState<DevUserState>({ phase: "loading" });
  const [dueItems, setDueItems] = useState<ReviewDueItem[] | null>(null);
  const [active, setActive] = useState<ReviewSessionResponse | null>(null);
  const [helpLevel, setHelpLevel] = useState<"none" | "hint" | "editorial">("none");
  const [submitting, setSubmitting] = useState<OutcomeKey | null>(null);
  const [result, setResult] = useState<CompleteReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  useEffect(() => {
    let cancelled = false;
    ensureDevUser().then((userId) => {
      if (cancelled) return;
      setDevUser(userId ? { phase: "ready", userId } : { phase: "error" });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshDue = useCallback(async (userId: string) => {
    try {
      setDueItems((await listDueReviews(userId)).items);
    } catch {
      setDueItems(null);
    }
  }, []);

  // Deep link support: /review?problem=<id> starts a review for one
  // solved problem (the dashboard table links here). Read via
  // window.location so prerendering needs no Suspense boundary.
  useEffect(() => {
    if (devUser.phase !== "ready" || active || result) return;
    const problemId = new URLSearchParams(window.location.search).get("problem");
    if (problemId) {
      begin(devUser.userId, problemId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [devUser]);

  useEffect(() => {
    if (devUser.phase !== "ready") return;
    const timer = setTimeout(() => refreshDue(devUser.userId), 0);
    return () => clearTimeout(timer);
  }, [devUser, refreshDue, result]); // refresh after each completed review

  async function begin(userId: string, problemId: string) {
    setError(null);
    setConflict(false);
    setResult(null);
    setHelpLevel("none");
    try {
      setActive(await startReview(userId, { problem_id: problemId }));
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "Could not start the review.");
    }
  }

  async function submit(userId: string, sessionId: string, outcome: OutcomeKey) {
    setSubmitting(outcome);
    setError(null);
    setConflict(false);
    try {
      const response = await completeReview(userId, sessionId, {
        outcome,
        independent: helpLevel === "none" ? true : false,
        help_level: helpLevel,
      });
      setResult(response);
      setActive(null);
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

      {devUser.phase === "error" ? (
        <section role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-900/60 bg-rose-950/40 p-5">
          <p className="text-sm text-rose-200">
            Could not reach the API. Start the backend (uvicorn on port 8000) and
            reload this page.
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
                  onClick={() => submit(devUser.userId, active.session.id, outcome.key)}
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
          <section aria-label="Due reviews" className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
            <h2 className="text-base font-semibold">Due for review</h2>
            {dueItems === null ? (
              <p className="text-sm text-slate-400">
                Could not load the review queue. Check the API is running.
              </p>
            ) : dueItems.length === 0 ? (
              <p className="text-sm text-slate-400">
                Nothing due right now. Reviews you complete will schedule
                themselves here — a Codeforces acceptance alone never creates a
                review.
              </p>
            ) : (
              <ul className="divide-y divide-slate-800">
                {dueItems.map((item) => (
                  <li key={item.problem.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-slate-100">
                        {item.problem.contest_id
                          ? `${item.problem.contest_id}${item.problem.problem_index} — ${item.problem.name}`
                          : item.problem.name}
                      </p>
                      <p className="text-xs text-slate-500">
                        due {item.due_at.slice(0, 16).replace("T", " ")} UTC ·{" "}
                        {item.repetitions} review{item.repetitions === 1 ? "" : "s"}
                        {item.lapses > 0 ? ` · ${item.lapses} lapse${item.lapses === 1 ? "" : "s"}` : ""}
                      </p>
                    </div>
                    <Button onClick={() => begin(devUser.userId, item.problem.id)}>
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
