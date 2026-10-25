"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  DashboardSummaryResponse,
  HeatmapMode,
  HeatmapResponse,
  SolvedProblemListResponse,
} from "@codepilot/contracts";
import { Heatmap } from "@/components/dashboard/heatmap";
import { SolvedTable, type TableState } from "@/components/dashboard/solved-table";
import { SummaryCards } from "@/components/dashboard/summary-cards";
import { Button } from "@/components/ui/button";
import { listAccounts } from "@/lib/codeforces";
import {
  getDashboardSummary,
  getHeatmap,
  listSolvedProblemsFiltered,
} from "@/lib/dashboard";
import { bootstrapSession, logout, type SessionState } from "@/lib/auth";

const HEATMAP_DAYS = 182;
const CURATED_TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Tokyo",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
];

type SessionPageState =
  | { phase: "loading" }
  | { phase: "anon" }
  | { phase: "unreachable" }
  | { phase: "ready"; displayName: string };

function localDateIn(tz: string, offsetDays = 0): string {
  const ms = Date.now() + offsetDays * 86_400_000;
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, dateStyle: "short" }).format(
    new Date(ms),
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [devUser, setDevUser] = useState<SessionPageState>({ phase: "loading" });
  // "none" is a real empty state; "error" means we do not know (API down) —
  // never conflate the two.
  const [accountGate, setAccountGate] = useState<"loading" | "none" | "error" | "has">("loading");
  const [timezone, setTimezone] = useState("UTC");
  const [mode, setMode] = useState<HeatmapMode>("submissions");
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [table, setTable] = useState<SolvedProblemListResponse | null>(null);
  const [tableLoading, setTableLoading] = useState(true);
  const [tableError, setTableError] = useState<string | null>(null);
  const [tableState, setTableState] = useState<TableState>({
    search: "",
    tag: "",
    ratingMin: "",
    ratingMax: "",
    page: 1,
  });

  const timezoneOptions = useMemo(() => {
    const detected =
      typeof Intl !== "undefined"
        ? Intl.DateTimeFormat().resolvedOptions().timeZone
        : "UTC";
    return Array.from(new Set([detected, ...CURATED_TIMEZONES]));
  }, []);

  // --- dev session bootstrap ------------------------------------------
  useEffect(() => {
    let cancelled = false;
    bootstrapSession().then((state: SessionState) => {
      if (cancelled) return;
      if (state.phase === "auth") {
        setDevUser({ phase: "ready", displayName: state.user.display_name });
      } else {
        setDevUser({ phase: state.phase });
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (devUser.phase !== "ready") return;
    let cancelled = false;
    listAccounts()
      .then((accounts) => {
        if (!cancelled) setAccountGate(accounts.length > 0 ? "has" : "none");
      })
      .catch(() => {
        if (!cancelled) setAccountGate("error");
      });
    return () => {
      cancelled = true;
    };
  }, [devUser]);

  // --- summary + heatmap -----------------------------------------------
  const loadOverview = useCallback(async () => {
      try {
        setSummary(await getDashboardSummary(timezone));
        setHeatmap(
          await getHeatmap({
            from: localDateIn(timezone, -(HEATMAP_DAYS - 1)),
            to: localDateIn(timezone),
            timezone,
            mode,
          }),
        );
      } catch {
        setSummary(null);
        setHeatmap(null);
      }
  }, [timezone, mode]);

  // Load the overview when an account exists OR when we could not tell
  // (outage): each section then reports its own honest unavailable state.
  const showDashboard = accountGate === "has" || accountGate === "error";

  useEffect(() => {
    if (devUser.phase !== "ready" || !showDashboard) return;
    const timer = setTimeout(() => loadOverview(), 0);
    return () => clearTimeout(timer);
  }, [devUser, showDashboard, loadOverview]);

  // --- table with debounced filters ------------------------------------
  useEffect(() => {
    if (devUser.phase !== "ready" || !showDashboard) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      setTableLoading(true);
      listSolvedProblemsFiltered({
        search: tableState.search || undefined,
        tag: tableState.tag || undefined,
        rating_min: tableState.ratingMin ? Number(tableState.ratingMin) : undefined,
        rating_max: tableState.ratingMax ? Number(tableState.ratingMax) : undefined,
        page: tableState.page,
        page_size: 10,
      })
        .then((data) => {
          if (cancelled) return;
          setTable(data);
          setTableError(null);
        })
        .catch(() => {
          if (cancelled) return;
          setTable(null);
          setTableError("Could not load solved problems. The API may be waking up — retry shortly.");
        })
        .finally(() => {
          if (!cancelled) setTableLoading(false);
        });
    }, tableState.search || tableState.tag || tableState.ratingMin || tableState.ratingMax ? 300 : 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [devUser, showDashboard, tableState]);

  const heatFrom = localDateIn(timezone, -(HEATMAP_DAYS - 1));
  const heatTo = localDateIn(timezone);

  return (
    <main className="mx-auto flex min-h-dvh max-w-6xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
            ← CodePilot Recall
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-400">
            Timezone
            <select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="field-input w-auto py-1.5"
            >
              {timezoneOptions.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                  {tz === timezoneOptions[0] ? " (detected)" : ""}
                </option>
              ))}
            </select>
          </label>
          <Link
            href="/review"
            className="inline-flex items-center justify-center rounded-lg bg-indigo-500 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-indigo-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
          >
            Review queue
          </Link>
          <span className="hidden text-sm text-slate-500 sm:inline">
            {devUser.phase === "ready" ? devUser.displayName : ""}
          </span>
          <Button
            variant="ghost"
            onClick={async () => {
              await logout();
              router.push("/login");
            }}
          >
            Log out
          </Button>
          <Link
            href="/onboarding"
            className="text-sm text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline"
          >
            Manage handle
          </Link>
        </div>
      </header>

      {devUser.phase === "loading" ? (
        <p role="status" className="text-sm text-slate-400">
          Preparing local session…
        </p>
      ) : null}

      {devUser.phase === "anon" ? (
        <section className="panel flex flex-col items-start gap-3 p-6">
          <h2 className="text-lg font-semibold tracking-tight">Log in to see your dashboard</h2>
          <p className="text-sm text-slate-400">
            Your activity, heatmap, and reviews are tied to your account.
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

      {devUser.phase === "ready" && accountGate === "none" ? (
        <section className="flex flex-col items-start gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-6">
          <h2 className="text-lg font-semibold">No Codeforces handle connected</h2>
          <p className="text-sm text-slate-400">
            Connect a handle and import your history to unlock the dashboard.
          </p>
          <Link
            href="/onboarding"
            className="inline-flex items-center justify-center rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
          >
            Connect your handle
          </Link>
        </section>
      ) : null}

      {devUser.phase === "ready" && showDashboard ? (
        <>
          {!summary ? (
            <p role="status" className="text-sm text-amber-300">
              Summary unavailable — the API could not be reached. Data below may
              be stale or empty.
            </p>
          ) : null}
          <SummaryCards summary={summary} />

          <Heatmap
            heatmap={heatmap}
            mode={mode}
            onModeChange={setMode}
            loading={!heatmap && !!summary}
          />

          <SolvedTable
            data={table}
            state={tableState}
            onStateChange={setTableState}
            loading={tableLoading}
            error={tableError}
          />

          <p className="text-xs text-slate-600">
            Heatmap range {heatFrom} → {heatTo} · activity dates are local to{" "}
            {timezone}. First-solve dates never move forward when older
            submissions are discovered.
          </p>
        </>
      ) : null}
    </main>
  );
}
