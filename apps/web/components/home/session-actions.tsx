"use client";

/**
 * Session-aware homepage actions (Phase 6).
 *
 * Uses bootstrapSession() and never conflates its states: while the
 * session is being resolved nothing is claimed, an unreachable API is
 * shown explicitly (it is NOT treated as logged out), and the
 * authenticated actions only appear once the session is validated.
 * Whether a Codeforces handle is linked is determined with the existing
 * account-list helper after authentication is confirmed.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { bootstrapSession, logout, type SessionState } from "@/lib/auth";
import { listAccounts } from "@/lib/codeforces";

type Phase = "loading" | "anon" | "unreachable" | "authed";
type AccountGate = "loading" | "has" | "none" | "error";

const primaryClasses =
  "inline-flex items-center justify-center rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400";
const secondaryClasses =
  "inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 transition-colors hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400";

export function SessionActions() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("loading");
  const [accountGate, setAccountGate] = useState<AccountGate>("loading");
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    bootstrapSession().then((state: SessionState) => {
      if (cancelled) return;
      if (state.phase === "auth") {
        setPhase("authed");
      } else {
        // anon and unreachable stay distinct; a network failure is never
        // treated as proof of being logged out.
        setPhase(state.phase);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    if (phase !== "authed") return;
    let cancelled = false;
    listAccounts()
      .then((accounts) => {
        if (cancelled) return;
        setAccountGate(accounts.length > 0 ? "has" : "none");
      })
      .catch(() => {
        if (cancelled) return;
        setAccountGate("error");
      });
    return () => {
      cancelled = true;
    };
  }, [phase]);

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await logout();
      // We are already on the public homepage: flip to honest anonymous
      // actions and navigate so the URL/page state is coherent.
      setPhase("anon");
      setAccountGate("none");
      router.push("/");
    } catch {
      setLogoutError("Log out failed — please try again.");
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div
      role="group"
      aria-label="Account actions"
      aria-busy={phase === "loading" || (phase === "authed" && accountGate === "loading")}
      className="flex flex-wrap items-center gap-3"
    >
      {phase === "loading" ? (
        <>
          <span className="sr-only">Checking your session…</span>
          <span aria-hidden className="h-9 w-28 animate-pulse rounded-lg bg-slate-800/60" />
        </>
      ) : null}

      {phase === "unreachable" ? (
        <>
          <p role="status" className="text-sm text-slate-400">
            Session status unavailable.
          </p>
          <Button variant="secondary" onClick={() => setReloadKey((key) => key + 1)}>
            Retry
          </Button>
        </>
      ) : null}

      {phase === "anon" ? (
        <>
          <Link href="/register" className={primaryClasses}>
            Get started
          </Link>
          <Link href="/login" className={secondaryClasses}>
            Log in
          </Link>
        </>
      ) : null}

      {phase === "authed" && accountGate === "loading" ? (
        <>
          <span className="sr-only">Checking linked accounts…</span>
          <span aria-hidden className="h-9 w-28 animate-pulse rounded-lg bg-slate-800/60" />
        </>
      ) : null}

      {phase === "authed" && (accountGate === "has" || accountGate === "error" || accountGate === "none") ? (
        <>
          {accountGate === "has" ? (
            <Link href="/dashboard" className={primaryClasses}>
              Open dashboard
            </Link>
          ) : null}
          {accountGate === "none" ? (
            <Link href="/onboarding" className={primaryClasses}>
              Connect your handle
            </Link>
          ) : null}
          {accountGate === "has" ? (
            <Link href="/onboarding" className={secondaryClasses}>
              Manage handle
            </Link>
          ) : null}
          {accountGate === "has" ? (
            <Link href="/review" className={secondaryClasses}>
              Review queue
            </Link>
          ) : null}
          {accountGate === "error" || accountGate === "none" ? (
            <Link href="/dashboard" className={primaryClasses}>
              Open dashboard
            </Link>
          ) : null}
          <Button variant="ghost" onClick={handleLogout} disabled={loggingOut}>
            {loggingOut ? "Logging out…" : "Log out"}
          </Button>
          {logoutError ? (
            <p role="alert" className="text-sm text-rose-300">
              {logoutError}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
