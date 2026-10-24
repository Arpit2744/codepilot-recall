"use client";

import { useState } from "react";
import type { AccountCreatedResponse } from "@codepilot/contracts";
import { createAccount } from "@/lib/codeforces";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

const HANDLE_PATTERN = /^[A-Za-z0-9_.-]{1,24}$/;

export function ConnectForm({
  onConnected,
}: {
  onConnected: (result: AccountCreatedResponse) => void;
}) {
  const [handle, setHandle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const trimmed = handle.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!HANDLE_PATTERN.test(trimmed)) {
      setError("Handles use 1-24 letters, digits, dot, underscore or hyphen.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await createAccount({ handle: trimmed });
      onConnected(result);
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 409) {
        setError("That handle is already linked to an account.");
      } else if (exc instanceof ApiError && exc.code === "validation_error") {
        setError("That handle doesn't look like a Codeforces handle.");
      } else {
        setError("Could not reach the API. Is the backend running on port 8000?");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex max-w-md flex-col gap-3" noValidate>
      <label htmlFor="cf-handle" className="text-sm font-medium text-slate-200">
        Codeforces handle
      </label>
      <div className="flex gap-2">
        <input
          id="cf-handle"
          name="handle"
          value={handle}
          onChange={(event) => setHandle(event.target.value)}
          placeholder="tourist"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error ? "true" : "false"}
          aria-describedby={error ? "cf-handle-error" : undefined}
          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-400 focus:outline-none"
        />
        <Button type="submit" disabled={submitting || trimmed.length === 0}>
          {submitting ? "Linking…" : "Connect"}
        </Button>
      </div>
      <p className="text-xs text-slate-500">
        Only the public handle — we never ask for your Codeforces password.
      </p>
      {error ? (
        <p id="cf-handle-error" role="alert" className="text-sm text-rose-400">
          {error}
        </p>
      ) : null}
    </form>
  );
}
