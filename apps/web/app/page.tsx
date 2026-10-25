import { ApiStatus } from "@/components/api-status";
import { SessionActions } from "@/components/home/session-actions";

const features = [
  {
    title: "True first-solve dates",
    body: "Imports your Codeforces history and keeps the date each problem was first accepted — revisions never overwrite it.",
  },
  {
    title: "Activity heatmap",
    body: "See submissions, first solves, and review sessions per day, bucketed in your own timezone.",
  },
  {
    title: "Adaptive revision",
    body: "An FSRS-based scheduler learns from your recall outcomes and spaces reviews so patterns stick for years.",
  },
] as const;

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-5xl flex-col gap-16 px-6 py-16">
      <header className="flex flex-col gap-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden
              className="flex size-7 items-center justify-center rounded-md border border-indigo-500/30 bg-indigo-500/10 font-mono text-xs font-semibold text-indigo-300"
            >
              &lt;/&gt;
            </span>
            <span className="text-sm font-semibold tracking-tight text-slate-200">
              CodePilot Recall
            </span>
          </div>
          <ApiStatus />
        </div>
        <div className="flex flex-col gap-5">
          <h1 className="max-w-3xl text-4xl font-bold leading-[1.1] tracking-tight sm:text-5xl lg:text-6xl">
            Remember every problem you&apos;ve solved.
          </h1>
          <p className="max-w-2xl text-lg leading-relaxed text-slate-400">
            CodePilot Recall connects to your Codeforces handle, preserves your
            solve history, and schedules personalized revision sessions with a
            spaced-repetition model that adapts to how well you actually recall
            each problem.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <a
            href="#features"
            className="inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 transition-colors hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
          >
            How it works
          </a>
          <SessionActions />
        </div>
      </header>

      <section id="features" className="grid gap-5 sm:grid-cols-3">
        {features.map((feature, index) => (
          <article
            key={feature.title}
            className="panel flex flex-col gap-3 p-6 transition-colors duration-150 hover:border-slate-700"
          >
            <span
              aria-hidden
              className="font-mono text-xs font-semibold tracking-widest text-teal-300/80"
            >
              {String(index + 1).padStart(2, "0")}
            </span>
            <h2 className="text-base font-semibold tracking-tight text-slate-100">
              {feature.title}
            </h2>
            <p className="text-sm leading-relaxed text-slate-400">
              {feature.body}
            </p>
          </article>
        ))}
      </section>

      <footer className="mt-auto flex flex-col gap-2 border-t border-slate-800/80 pt-6 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <p>CodePilot Recall · not affiliated with Codeforces</p>
        <p className="text-xs">Free-tier beta · sessions secured with HttpOnly cookies</p>
      </footer>
    </main>
  );
}
