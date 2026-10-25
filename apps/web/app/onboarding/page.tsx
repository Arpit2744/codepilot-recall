"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { SolvedProblemListResponse, SyncStatusResponse } from "@codepilot/contracts";
import { ConnectForm } from "@/components/codeforces/connect-form";
import { SolvedList } from "@/components/codeforces/solved-list";
import { SyncPanel } from "@/components/codeforces/sync-panel";
import { Button } from "@/components/ui/button";
import { getSyncStatus, listAccounts, listSolvedProblems, triggerSync } from "@/lib/codeforces";
import { bootstrapSession, type SessionState } from "@/lib/auth";

type SessionPageState =
  | { phase: "loading" }
  | { phase: "anon" }
  | { phase: "unreachable" }
  | { phase: "ready"; userId: string };

export default function OnboardingPage() {
  const [devUser, setDevUser] = useState<SessionPageState>({ phase: "loading" });
  const [accountId, setAccountId] = useState<string | null>(null);
  const [status, setStatus] = useState<SyncStatusResponse | null>(null);
  const [problems, setProblems] = useState<SolvedProblemListResponse | null>(null);
  const [syncing, setSyncing] = useState(false);

  // --- dev user bootstrap ---------------------------------------------
  useEffect(() => {
    let cancelled = false;
    bootstrapSession().then((state: SessionState) => {
      if (cancelled) return;
      if (state.phase === "auth") {
        setDevUser({ phase: "ready", userId: state.user.id });
      } else {
        setDevUser({ phase: state.phase }); // anon | unreachable
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // When a dev user exists, show their first linked account (Phase 1: one
  // account per user in practice; the API enforces one owner per handle).
  useEffect(() => {
    if (devUser.phase !== "ready") return;
    let cancelled = false;
    listAccounts()
      .then((accounts) => {
        if (!cancelled && accounts.length > 0) setAccountId(accounts[0].id);
      })
      .catch(() => {
        /* API down: the reachability banner reports it. */
      });
    return () => {
      cancelled = true;
    };
  }, [devUser]);

  // --- sync status polling + solved problems ---------------------------
  const refreshStatus = useCallback(async (id: string) => {
    try {
      const next = await getSyncStatus(id);
      setStatus(next);
      const latest = next.latest_jobs[0];
      if (latest?.status === "succeeded") {
        setProblems(await listSolvedProblems());
      }
    } catch {
      /* transient poll failure: next tick retries */
    }
  }, []);

  useEffect(() => {
    if (devUser.phase !== "ready" || !accountId) return;
    const poll = () => refreshStatus(accountId);
    // First poll deferred a tick so no setState runs synchronously in the effect.
    const first = setTimeout(poll, 0);
    const timer = setInterval(poll, 3000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [devUser, accountId, refreshStatus]);

  async function handleSyncNow() {
    if (devUser.phase !== "ready" || !accountId) return;
    setSyncing(true);
    try {
      await triggerSync(accountId);
      await refreshStatus(accountId);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-2">
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
          ← CodePilot Recall
        </Link>
        <h1 className="text-3xl font-bold tracking-tight">Connect Codeforces</h1>
        <p className="text-slate-400">
          Link your public handle to import your submission history and keep
          first-solve dates.
        </p>
      </header>

      {devUser.phase === "loading" ? (
        <p role="status" className="text-sm text-slate-400">
          Preparing local session…
        </p>
      ) : null}

      {devUser.phase === "anon" ? (
        <section className="flex flex-col items-start gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-6">
          <h2 className="text-lg font-semibold">Log in to connect a handle</h2>
          <p className="text-sm text-slate-400">
            Create an account or log in to link your Codeforces handle.
          </p>
          <div className="flex gap-2">
            <a
              href="/login"
              className="inline-flex items-center justify-center rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400"
            >
              Log in
            </a>
            <a
              href="/register"
              className="inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-700"
            >
              Create account
            </a>
          </div>
        </section>
      ) : null}

      {devUser.phase === "unreachable" ? (
        <section
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-rose-900/60 bg-rose-950/40 p-5"
        >
          <p className="text-sm text-rose-200">
            Could not reach the API to start a local session. Start the backend
            (uvicorn on port 8000) and reload this page.
          </p>
          <div>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        </section>
      ) : null}

      {devUser.phase === "ready" ? (
        <>
          {!accountId ? (
            <ConnectForm
              onConnected={(result) => setAccountId(result.account.id)}
            />
          ) : (
            <>
              <SyncPanel status={status} onSyncNow={handleSyncNow} syncing={syncing} />
              <SolvedList problems={problems} />
            </>
          )}
        </>
      ) : null}
    </main>
  );
}
