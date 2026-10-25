import type { DashboardSummaryResponse } from "@codepilot/contracts";

export function SummaryCards({ summary }: { summary: DashboardSummaryResponse | null }) {
  if (!summary) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="panel h-24 animate-pulse"
          />
        ))}
      </div>
    );
  }

  const cards = [
    { label: "Submissions", value: summary.totals.submissions },
    { label: "Problems solved", value: summary.totals.solved_problems },
    { label: "Current streak", value: `${summary.current_streak_days}d`, accent: true },
    { label: "Linked handles", value: summary.accounts.length },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="panel flex flex-col gap-1 p-5">
          <p className="micro-label">{card.label}</p>
          <p
            className={`text-3xl font-semibold tracking-tight ${
              card.accent ? "text-teal-300" : "text-slate-50"
            }`}
          >
            {card.value}
          </p>
        </div>
      ))}
    </div>
  );
}
