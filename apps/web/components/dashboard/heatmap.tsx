"use client";

import type { HeatmapMode, HeatmapResponse } from "@codepilot/contracts";

const MODE_LABELS: Record<HeatmapMode, string> = {
  submissions: "Submissions",
  first_solves: "First solves",
  reviews: "Reviews",
};

const WEEKDAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];

function intensity(count: number, max: number): string {
  if (count === 0) return "bg-slate-800/70";
  if (max <= 1 || count <= max / 4) return "bg-indigo-900";
  if (count <= max / 2) return "bg-indigo-700";
  if (count <= (max * 3) / 4) return "bg-indigo-500";
  return "bg-indigo-300";
}

/**
 * GitHub-style calendar grid. Weeks run Monday-first; the visual grid is
 * decorative and each cell carries its count via title + a screen-reader
 * friendly summary paragraph.
 */
export function Heatmap({
  heatmap,
  mode,
  onModeChange,
  loading,
}: {
  heatmap: HeatmapResponse | null;
  mode: HeatmapMode;
  onModeChange: (mode: HeatmapMode) => void;
  loading: boolean;
}) {
  const modes: HeatmapMode[] = ["submissions", "first_solves", "reviews"];

  const days = heatmap?.days ?? [];
  const max = heatmap?.max_count ?? 0;

  // Pad the first week so columns align on Mondays.
  const firstWeekday = days.length ? new Date(days[0].date).getUTCDay() : 1;
  const leading = (firstWeekday + 6) % 7; // Monday=0
  const cells: (typeof days[number] | null)[] = [
    ...Array.from({ length: leading }, () => null),
    ...days,
  ];
  const weeks: (typeof cells)[] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));

  const monthLabels = weeks.map((week) => {
    const first = week.find((d) => d !== null);
    if (!first) return "";
    const date = new Date(first.date);
    return date.getUTCDate() <= 7
      ? date.toLocaleDateString("en", { month: "short", timeZone: "UTC" })
      : "";
  });

  return (
    <section
      aria-label="Activity heatmap"
      className="panel flex flex-col gap-4 p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-semibold tracking-tight">Activity</h2>
        <div
          role="tablist"
          aria-label="Activity mode"
          className="inline-flex gap-0.5 rounded-lg border border-slate-800 bg-slate-950/70 p-1"
        >
          {modes.map((m) => {
            const selected = mode === m;
            return (
              <button
                key={m}
                role="tab"
                aria-selected={selected}
                onClick={() => onModeChange(m)}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 ${
                  selected
                    ? "bg-indigo-500/90 text-white"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                }`}
              >
                {MODE_LABELS[m]}
              </button>
            );
          })}
        </div>
      </div>

      {loading ? (
        <div aria-busy="true" className="h-28 animate-pulse rounded-lg bg-slate-950/60" />
      ) : !heatmap ? (
        <p className="text-sm text-slate-400">Activity unavailable right now.</p>
      ) : !heatmap.available ? (
        <div role="status" className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-sm text-slate-300">Reviews: coming in Phase 3</p>
          <p className="mt-1 text-xs text-slate-500">{heatmap.message}</p>
        </div>
      ) : (
        <>
          <p className="sr-only">
            Activity heatmap in {heatmap.mode.replace("_", " ")} mode from {heatmap.from} to{" "}
            {heatmap.to} in {heatmap.timezone}. Peak day has {heatmap.max_count} items.
          </p>
          <div className="overflow-x-auto" role="img" aria-hidden="true">
            <div className="min-w-max">
              <div aria-hidden className="mb-1.5 flex gap-1">
                {monthLabels.map((label, i) => (
                  <div
                    key={i}
                    className="w-3 text-center text-[9px] font-medium uppercase tracking-wide text-slate-600"
                  >
                    {label}
                  </div>
                ))}
              </div>
              <div className="flex gap-3">
                <div className="grid grid-rows-7 gap-1">
                  {WEEKDAY_LABELS.map((label, i) => (
                    <div key={i} className="h-3 text-[10px] leading-3 text-slate-500">
                      {label}
                    </div>
                  ))}
                </div>
                <div className="flex gap-1">
                  {weeks.map((week, wi) => (
                    <div key={wi} className="grid grid-rows-7 gap-1">
                      {Array.from({ length: 7 }, (_, di) => {
                        const day = week[di] ?? null;
                        return (
                          <div
                            key={di}
                            title={day ? `${day.date}: ${day.count}` : undefined}
                            className={`h-3 w-3 rounded-[3px] transition-colors ${
                              day ? intensity(day.count, max) : "bg-slate-800/50"
                            } ${day ? "hover:ring-1 hover:ring-slate-500" : ""}`}
                          />
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-3 flex items-center gap-1.5 text-[10px] font-medium text-slate-500">
                <span>Less</span>
                <span className="size-3 rounded-[3px] bg-slate-800/50 ring-1 ring-inset ring-slate-800" />
                <span className="size-3 rounded-[3px] bg-indigo-900" />
                <span className="size-3 rounded-[3px] bg-indigo-700" />
                <span className="size-3 rounded-[3px] bg-indigo-500" />
                <span className="size-3 rounded-[3px] bg-indigo-300" />
                <span>More</span>
              </div>
            </div>
          </div>
          <p className="border-t border-slate-800/60 pt-3 text-xs text-slate-500">
            Dates are local calendar days in {heatmap.timezone}.
          </p>
        </>
      )}
    </section>
  );
}
