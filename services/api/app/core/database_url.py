"""Connection-string normalization for PostgreSQL URLs (Phase 6).

Neon issues ``postgresql://`` URLs, while this project speaks SQLAlchemy's
psycopg 3 dialect (``postgresql+psycopg://``), and Neon requires TLS.
Normalization is deliberately conservative:

- ``postgres://`` / ``postgresql://`` schemes become
  ``postgresql+psycopg://``; already driver-qualified URLs pass through
  with their scheme untouched.
- For Neon hosts, ``sslmode=require`` is appended ONLY when the URL has no
  ``sslmode`` parameter — existing query parameters (and any explicit
  sslmode) are preserved.
- Credentials, host, port, database name, and unrelated query parameters
  are never rebuilt or reordered; the netloc and path pass through
  verbatim.
- Non-PostgreSQL URLs (e.g. the SQLite URLs used in tests and local
  runs) are returned unchanged, so local development and CI behavior is
  unaffected.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_DRIVER_SCHEME = "postgresql+psycopg"


def normalize_database_url(url: str | None) -> str | None:
    """Return `url` normalized for the installed psycopg 3 driver."""
    if not url:
        return url
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    is_postgres = scheme in ("postgres", "postgresql") or scheme.startswith(
        "postgresql+"
    )
    if not is_postgres:
        return url

    new_scheme = (
        _DRIVER_SCHEME if scheme in ("postgres", "postgresql") else parts.scheme
    )

    # parse_qsl keeps duplicates; urlencode re-emits them in order, so no
    # query parameter (e.g. Neon's options=project%3D...) is lost.
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    hostname = (parts.hostname or "").lower()
    if hostname.endswith("neon.tech") and "sslmode" not in {k for k, _ in pairs}:
        pairs.append(("sslmode", "require"))

    return urlunsplit((new_scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))
