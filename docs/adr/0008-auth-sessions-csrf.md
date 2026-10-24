# ADR-0008: Server-side sessions, Argon2id, and CSRF (Phase 5)

Date: 2026-10-25 · Status: accepted

## Context

Phases 1–4 used an explicitly non-authentic `X-User-Id` development header
(production returned 401 for everything). Phase 5 replaces it with real
email/password authentication. No external identity requirement exists, so
local auth with server-side sessions fits the existing stack.

## Decisions

1. **Passwords: Argon2id** via `argon2-cffi==25.1.0` (pinned; benchmarked
   ~120ms hash/verify at the default `m=64MiB, t=2, p=4` — the OWASP
   guidance class for this cost). Parameters are Settings-configurable so
   CI/tests use an identical-code fast profile without weakening
   production. Hashes are never logged or returned. Login responses are
   uniform for unknown-email and wrong-password; unknown-email burns a
   dummy Argon2 verification for timing parity.
2. **Sessions: opaque 256-bit tokens** (`secrets.token_urlsafe(32)`),
   HttpOnly cookies; only `sha256(token)` is stored (`user_sessions`,
   migration `0005`). Absolute lifetime 30d, inactivity 7d, `last_seen_at`
   sliding (throttled to 1/min). Logout/revoke-all set `revoked_at`; a
   cookie alone never authorizes anything — every request revalidates hash,
   expiry, inactivity, revocation, and user existence.
3. **Cookies:** `HttpOnly; SameSite=Lax; Path=/` always, host-only (no
   `Domain`). Production adds `Secure` and the `__Host-` prefix
   (`__Host-cpr_session`); local HTTP dev uses the plain name. Production
   never weakens these for localhost.
4. **CSRF: synchronizer token.** Each session has a 32-byte token stored
   hashed; `GET /auth/csrf` mints a fresh one (rotation on fetch) to the
   authenticated owner only. All state-changing application requests must
   echo it in `X-CSRF-Token` (compared with `secrets.compare_digest`).
   Defense-in-depth: Origin (Referer fallback) must match a configured
   origin when present; browsers always send Origin on cross-site
   mutations, so header-less non-browser clients pass (they are not
   CSRF-exposed). SameSite=Lax alone is never the whole defense, and
   GET/HEAD never mutate state.
5. **Rate limiting:** shared fixed-window Redis limiter
   (`register` 5/h/IP; `login` 10/15m/IP and per-email). If Redis is
   unreachable in production, auth endpoints fail CLOSED (503) rather than
   degrade to per-process counters; non-production falls back in-process.
   Keys use endpoint + socket peer IP — **not** `X-Forwarded-For` (trusting
   it requires a documented trusted proxy; documented in deployment.md).
   429s carry `Retry-After`.
6. **Dev-era users** (created by the removed bootstrap, `password_hash`
   NULL) can never log in, are never auto-assigned passwords, and their
   data is preserved untouched. No public takeover path exists; an admin
   conversion procedure is deliberately out of scope.
7. **Email verification / password reset are deferred** — no mail provider
   exists in this deployment; both flows are documented as not present
   rather than faked.
8. **Quota:** max linked Codeforces handles per user (default 5,
   configurable) — one knob, no arbitrary revision limits.

## Limitations (explicit)

- No professional security audit or penetration test has been performed;
  green CI is necessary evidence, not proof of security.
- Audit events are structured JSON logs (registration/login/logout/
  revocation/rate-limit decisions) — no credentials or tokens in them.
- `GET /auth/sessions` exposes metadata only (timestamps, `current` flag).
