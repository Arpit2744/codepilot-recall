"use client";

import { createDevUser } from "@/lib/codeforces";

const STORAGE_KEY = "cpr.dev-user-id";

/**
 * Resolve a dev user id for the Phase 1 auth boundary. Creates one via the
 * dev bootstrap endpoint on first use and remembers it in localStorage.
 * Returns null when the API is unreachable (caller shows a retry affordance).
 */
export async function ensureDevUser(): Promise<string | null> {
  if (typeof window === "undefined") return null;

  let userId = window.localStorage.getItem(STORAGE_KEY);
  if (userId) return userId;

  try {
    const user = await createDevUser();
    userId = user.user_id;
    window.localStorage.setItem(STORAGE_KEY, userId);
    return userId;
  } catch {
    return null;
  }
}

export function clearDevUser(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}
