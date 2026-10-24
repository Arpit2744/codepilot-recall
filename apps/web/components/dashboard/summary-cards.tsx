"use client";

import type { DashboardSummaryResponse } from "@codepilot/contracts";

export function SummaryCards({ summary }: { summary: DashboardSummaryResponse | null }) {
  if (!summary) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-xl border border-slate-800 bg-slate-900/50"
          />
        ))}
      </div>
    );
  }

  const cards = [
    { label: "Submissions", value: summary.totals.submissions },
    { label: "Problems solved", value: summary.totals.solved_problems },
    { label: "Current streak", value: `${summary.current_streak_days}d` },
    { label: "Linked handles", value: summary.accounts.length },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-xl border border-slate-800 bg-slate-900/50 p-4"
        >
          <p className="text-xs uppercase tracking-wide text-slate-500">{card.label}</p>
          <p className="mt-1 text-2xl font-semibold text-slate-100">{card.value}</p>
        </div>
      ))}
    </div>
  );
}
