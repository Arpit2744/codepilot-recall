"use client";

import { useEffect, useState } from "react";
import type { HealthResponse } from "@codepilot/contracts";
import { apiFetch } from "@/lib/api";

type Status = "loading" | "ok" | "error";

const labels: Record<Status, string> = {
  loading: "Checking API…",
  ok: "API online",
  error: "API unreachable",
};

const dotColors: Record<Status, string> = {
  loading: "bg-slate-400 animate-pulse",
  ok: "bg-emerald-400",
  error: "bg-rose-400",
};

export function ApiStatus() {
  const [status, setStatus] = useState<Status>("loading");
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<HealthResponse>("/health")
      .then((health) => {
        if (cancelled) return;
        setStatus("ok");
        setVersion(health.version);
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <p
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1 text-xs text-slate-400"
    >
      <span aria-hidden className={`size-2 rounded-full ${dotColors[status]}`} />
      {labels[status]}
      {status === "ok" && version ? (
        <span className="text-slate-500">v{version}</span>
      ) : null}
    </p>
  );
}
