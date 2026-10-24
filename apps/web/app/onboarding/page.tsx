"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { SolvedProblemListResponse, SyncStatusResponse } from "@codepilot/contracts";
import { ConnectForm } from "@/components/codeforces/connect-form";
import { SolvedList } from "@/components/codeforces/solved-list";
import { SyncPanel } from "@/components/codeforces/sync-panel";
import { Button } from "@/components/ui/button";
import { getSyncStatus, listAccounts, listSolvedProblems, triggerSync } from "@/lib/codeforces";
import { ensureDevUser } from "@/lib/dev-user";

type DevUserState =
  | { phase: "loading" }
  | { phase: "error" }
  | { phase: "ready"; userId: string };

export default function OnboardingPage() {
  const [devUser, setDevUser] = useState<DevUserState>({ phase: "loading" });
  const [accountId, setAccountId] = useState<string | null>(null);
  const [status, setStatus] = useState<SyncStatusResponse | null>(null);
  const [problems, setProblems] = useState<SolvedProblemListResponse | null>(null);
  const [syncing, setSyncing] = useState(false);

  // --- dev user bootstrap ---------------------------------------------
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

  // When a dev user exists, show their first linked account (Phase 1: one
  // account per user in practice; the API enforces one owner per handle).
  useEffect(() => {
    if (devUser.phase !== "ready") return;
    let cancelled = false;
    listAccounts(devUser.userId)
      .then((accounts) => {
        if (!cancelled && accounts.length > 0) setAccountId(accounts[0].id);
      })
      .catch(() => {
        /* API down: the dev-user banner already reports reachability. */
      });
    return () => {
      cancelled = true;
    };
  }, [devUser]);

  // --- sync status polling + solved problems ---------------------------
  const refreshStatus = useCallback(async (userId: string, id: string) => {
    try {
      const next = await getSyncStatus(userId, id);
      setStatus(next);
      const latest = next.latest_jobs[0];
      if (latest?.status === "succeeded") {
        setProblems(await listSolvedProblems(userId));
      }
    } catch {
      /* transient poll failure: next tick retries */
    }
  }, []);

  useEffect(() => {
    if (devUser.phase !== "ready" || !accountId) return;
    const { userId } = devUser;
    const poll = () => refreshStatus(userId, accountId);
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
      await triggerSync(devUser.userId, accountId);
      await refreshStatus(devUser.userId, accountId);
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

      {devUser.phase === "error" ? (
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
              userId={devUser.userId}
              onConnected={(result) => setAccountId(result.account.id)}
            />
          ) : (
            <>
              <SyncPanel status={status} onSyncNow={handleSyncNow} syncing={syncing} />
              <SolvedList problems={problems} />
            </>
          )}

          <p className="text-xs text-slate-600">
            Development mode: identity is a local dev user until real
            authentication ships in Phase 5.
          </p>
        </>
      ) : null}
    </main>
  );
}
