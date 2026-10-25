import Link from "next/link";
import { ApiStatus } from "@/components/api-status";

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
      <header className="flex flex-col gap-6">
        <ApiStatus />
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Remember every problem you&apos;ve solved.
        </h1>
        <p className="max-w-2xl text-lg text-slate-400">
          CodePilot Recall connects to your Codeforces handle, preserves your
          solve history, and schedules personalized revision sessions with a
          spaced-repetition model that adapts to how well you actually recall
          each problem.
        </p>
        <div className="flex gap-3">
          <a
            href="#features"
            className="inline-flex items-center justify-center rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
          >
            How it works
          </a>
          <Link
            href="/onboarding"
            className="inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 transition-colors hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
          >
            Connect your handle
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 transition-colors hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
          >
            Open dashboard
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium text-slate-400 underline-offset-2 transition-colors hover:text-slate-200 hover:underline"
          >
            Log in
          </Link>
        </div>
      </header>

      <section id="features" className="grid gap-6 sm:grid-cols-3">
        {features.map((feature) => (
          <article
            key={feature.title}
            className="rounded-xl border border-slate-800 bg-slate-900/50 p-6"
          >
            <h2 className="mb-2 text-base font-semibold text-slate-100">
              {feature.title}
            </h2>
            <p className="text-sm leading-relaxed text-slate-400">
              {feature.body}
            </p>
          </article>
        ))}
      </section>

      <footer className="mt-auto border-t border-slate-800 pt-6 text-sm text-slate-500">
        CodePilot Recall · not affiliated with Codeforces
      </footer>
    </main>
  );
}
