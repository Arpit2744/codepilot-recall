"use client";

import type { SolvedProblemListResponse } from "@codepilot/contracts";

export function SolvedList({ problems }: { problems: SolvedProblemListResponse | null }) {
  return (
    <section
      aria-label="Solved problems"
      className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-5"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Solved problems</h2>
        <p className="text-sm text-slate-500">{problems ? `${problems.total} total` : ""}</p>
      </div>

      {!problems ? (
        <p className="text-sm text-slate-400">Nothing imported yet — run your first sync.</p>
      ) : problems.items.length === 0 ? (
        <p className="text-sm text-slate-400">
          No accepted submissions yet. They will appear here after a successful import.
        </p>
      ) : (
        <ul className="divide-y divide-slate-800">
          {problems.items.map((problem) => (
            <li key={problem.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                {problem.url ? (
                  <a
                    href={problem.url}
                    target="_blank"
                    rel="noreferrer"
                    className="truncate text-slate-100 underline-offset-2 hover:underline"
                  >
                    {problem.contest_id ? `${problem.contest_id}${problem.problem_index} — ` : ""}
                    {problem.name}
                  </a>
                ) : (
                  <span className="truncate text-slate-100">{problem.name}</span>
                )}
                <p className="truncate text-xs text-slate-500">
                  {problem.tags.slice(0, 3).join(" · ") || "no tags"}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-slate-300">{problem.rating ?? "—"}</p>
                <p className="text-xs text-slate-500">
                  solved {problem.first_solved_at.slice(0, 10)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
