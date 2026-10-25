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
        setError("Could not reach the API. It may be waking up — retry shortly.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="panel flex max-w-md flex-col gap-4 p-6" noValidate>
      <label htmlFor="cf-handle" className="flex flex-col gap-1.5">
        <span className="micro-label">Codeforces handle</span>
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
          className="field-input"
        />
      </label>
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting || trimmed.length === 0}>
          {submitting ? "Linking…" : "Connect"}
        </Button>
      </div>
      <p className="text-xs leading-relaxed text-slate-500">
        Only the public handle — we never ask for your Codeforces password.
        Imports run through a queued worker about every 4 hours.
      </p>
      {error ? (
        <p id="cf-handle-error" role="alert" className="text-sm text-rose-300">
          {error}
        </p>
      ) : null}
    </form>
  );
}
