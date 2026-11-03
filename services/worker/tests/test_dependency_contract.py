"""Dependency contract checks for worker runtime."""

import tomllib
from pathlib import Path


def test_worker_declares_packaging_for_celery_redis_transport():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert "packaging==26.3" in deps
