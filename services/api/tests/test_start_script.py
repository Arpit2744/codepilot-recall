"""start.sh contract tests (Phase 6): migrations gate uvicorn startup, the
direct Neon URL is used for migrations only, and the runtime DATABASE_URL
reaches the API process. The real script is executed with `sh` against
stub alembic/uvicorn commands — no Docker or database required."""

import os
import subprocess
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
START_SCRIPT = SERVICE_DIR / "scripts" / "start.sh"


def _write_stubs(bin_dir: Path, alembic_exit: int) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    # LF-only stubs; they run inside sh.
    (bin_dir / "alembic").write_text(
        "#!/bin/sh\n"
        'printf \'alembic|%s\\n\' "$DATABASE_URL" >> "$STUB_LOG"\n'
        f"exit {alembic_exit}\n",
        encoding="utf-8",
        newline="\n",
    )
    (bin_dir / "uvicorn").write_text(
        "#!/bin/sh\n"
        'printf \'uvicorn|%s|%s\\n\' "$*" "$DATABASE_URL" >> "$STUB_LOG"\n',
        encoding="utf-8",
        newline="\n",
    )


def _run_start(
    tmp_path: Path, *, alembic_exit: int = 0, direct_url: str | None = None
) -> tuple[subprocess.CompletedProcess, Path]:
    stub_bin = tmp_path / "bin"
    _write_stubs(stub_bin, alembic_exit=alembic_exit)
    log = tmp_path / "stub.log"
    sep = ";" if os.name == "nt" else ":"
    env = {
        **os.environ,
        "PATH": f"{stub_bin}{sep}{os.environ.get('PATH', '')}",
        "STUB_LOG": "stub.log",  # relative: resolved against cwd (tmp_path)
        "DATABASE_URL": "runtime-url",
        "PORT": "12345",
    }
    env.pop("DIRECT_DATABASE_URL", None)
    if direct_url is not None:
        env["DIRECT_DATABASE_URL"] = direct_url

    result = subprocess.run(
        ["sh", str(START_SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, log


def test_start_script_passes_shell_syntax_check():
    result = subprocess.run(
        ["sh", "-n", str(START_SCRIPT)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_direct_url_used_for_migrations_only(tmp_path):
    result, log = _run_start(tmp_path, direct_url="direct-url")

    assert result.returncode == 0, result.stderr
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert lines == [
        "alembic|direct-url",  # migrations used the direct URL
        # API process kept the runtime DATABASE_URL and honors PORT.
        "uvicorn|app.main:app --host 0.0.0.0 --port 12345|runtime-url",
    ]


def test_falls_back_to_runtime_database_url(tmp_path):
    result, log = _run_start(tmp_path)

    assert result.returncode == 0, result.stderr
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert lines == [
        "alembic|runtime-url",
        "uvicorn|app.main:app --host 0.0.0.0 --port 12345|runtime-url",
    ]


def test_migration_failure_stops_startup(tmp_path):
    result, log = _run_start(tmp_path, direct_url="direct-url", alembic_exit=1)

    assert result.returncode != 0  # non-zero exit: service never starts
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert lines == ["alembic|direct-url"]  # uvicorn was never executed
