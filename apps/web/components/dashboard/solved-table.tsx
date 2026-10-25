"use client";

import type { SolvedProblemListResponse } from "@codepilot/contracts";
import { Button } from "@/components/ui/button";

export interface TableState {
  search: string;
  tag: string;
  ratingMin: string;
  ratingMax: string;
  page: number;
}

export function SolvedTable({
  data,
  state,
  onStateChange,
  loading,
  error,
}: {
  data: SolvedProblemListResponse | null;
  state: TableState;
  onStateChange: (next: TableState) => void;
  loading: boolean;
  error: string | null;
}) {
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  function update(patch: Partial<TableState>) {
    onStateChange({ ...state, ...patch, page: patch.page ?? 1 });
  }

  return (
    <section
      aria-label="Solved problems"
      className="panel flex flex-col gap-4 p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold tracking-tight">Solved problems</h2>
        {data ? (
          <p className="text-sm text-slate-500">{data.total} total</p>
        ) : null}
      </div>

      <form
        className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(event) => event.preventDefault()}
      >
        <label className="flex flex-col gap-1.5">
          <span className="micro-label">Search name</span>
          <input
            value={state.search}
            onChange={(e) => update({ search: e.target.value })}
            placeholder="theatre"
            className="field-input py-1.5"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="micro-label">Tag</span>
          <input
            value={state.tag}
            onChange={(e) => update({ tag: e.target.value })}
            placeholder="dp"
            className="field-input py-1.5"
          />
        </label>
        <div className="flex items-end gap-2">
          <label className="flex flex-1 flex-col gap-1.5">
            <span className="micro-label">Rating min</span>
            <input
              type="number"
              min={0}
              max={10000}
              value={state.ratingMin}
              onChange={(e) => update({ ratingMin: e.target.value })}
              placeholder="800"
              className="field-input py-1.5"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1.5">
            <span className="micro-label">Rating max</span>
            <input
              type="number"
              min={0}
              max={10000}
              value={state.ratingMax}
              onChange={(e) => update({ ratingMax: e.target.value })}
              placeholder="3500"
              className="field-input py-1.5"
            />
          </label>
        </div>
      </form>

      {error ? (
        <p role="alert" className="rounded-lg border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
          {error}
        </p>
      ) : loading ? (
        <div aria-busy="true" className="h-32 animate-pulse rounded-lg bg-slate-950/60" />
      ) : !data || data.items.length === 0 ? (
        <p className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
          {data && data.total === 0
            ? "No solved problems match these filters."
            : "No solved problems yet — connect a handle and run an import."}
        </p>
      ) : (
        <div className="-mx-5 overflow-x-auto px-5">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <th scope="col" className="py-2 pr-2">Problem</th>
              <th scope="col" className="py-2 pr-2">Rating</th>
              <th scope="col" className="py-2 pr-2">Tags</th>
              <th scope="col" className="py-2 pr-2">First solved</th>
              <th scope="col" className="py-2 pr-2">Solves</th>
              <th scope="col" className="py-2">
                <span className="sr-only">Review</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((problem) => (
              <tr
                key={problem.id}
                className="border-b border-slate-800/50 transition-colors hover:bg-slate-900/40"
              >
                <td className="py-2 pr-2">
                  {problem.url ? (
                    <a
                      href={problem.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-slate-100 underline-offset-2 hover:underline"
                    >
                      {problem.contest_id
                        ? `${problem.contest_id}${problem.problem_index} — ${problem.name}`
                        : problem.name}
                    </a>
                  ) : (
                    <span className="text-slate-100">{problem.name}</span>
                  )}
                </td>
                <td className="py-2.5 pr-2 font-mono text-slate-300">{problem.rating ?? "—"}</td>
                <td className="py-2.5 pr-2 text-xs text-slate-500">
                  {problem.tags.slice(0, 3).join(" · ") || "—"}
                </td>
                <td className="py-2.5 pr-2 font-mono text-xs text-slate-400">
                  {problem.first_solved_at.slice(0, 10)}
                </td>
                <td className="py-2.5 pr-2 text-slate-400">{problem.accepted_count}</td>
                <td className="py-2">
                  <a
                    href={`/review?problem=${problem.id}`}
                    className="text-xs font-medium text-indigo-300 underline-offset-2 hover:text-indigo-200 hover:underline"
                  >
                    Review
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      {data && data.total > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-slate-500">
            Page {data.page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              disabled={data.page <= 1 || loading}
              onClick={() => onStateChange({ ...state, page: state.page - 1 })}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              disabled={data.page >= totalPages || loading}
              onClick={() => onStateChange({ ...state, page: state.page + 1 })}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
