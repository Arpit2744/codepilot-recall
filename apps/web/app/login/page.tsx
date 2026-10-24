"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { login } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login({ email: email.trim(), password });
      router.push("/dashboard");
    } catch (exc) {
      if (exc instanceof ApiError) {
        if (exc.status === 401) setError("Invalid email or password.");
        else if (exc.status === 429) setError("Too many attempts — please wait a moment and try again.");
        else setError(exc.message);
      } else {
        setError("Could not reach the API. Is the backend running on port 8000?");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-8 px-6 py-12">
      <header className="flex flex-col gap-1">
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
          ← CodePilot Recall
        </Link>
        <h1 className="text-3xl font-bold tracking-tight">Log in</h1>
      </header>

      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Email
          <input
            type="email"
            name="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 focus:border-indigo-400 focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-300">
          Password
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 focus:border-indigo-400 focus:outline-none"
          />
        </label>

        {error ? (
          <p role="alert" className="text-sm text-rose-300">
            {error}
          </p>
        ) : null}

        <Button type="submit" disabled={busy || !email || !password}>
          {busy ? "Logging in…" : "Log in"}
        </Button>
      </form>

      <p className="text-sm text-slate-400">
        No account yet?{" "}
        <Link href="/register" className="text-indigo-300 underline-offset-2 hover:underline">
          Create one
        </Link>
      </p>
    </main>
  );
}
