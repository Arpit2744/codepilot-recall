"""Fresh-database migration test: upgrade head, inspect, downgrade base.

Runs against a throwaway SQLite database locally; CI repeats it against a
real PostgreSQL service container.
"""

from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from app.models import Base

API_DIR = Path(__file__).resolve().parents[1]


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    # Explicit URL wins over settings (see alembic/env.py).
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_creates_expected_schema(tmp_path):
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    engine.dispose()

    assert "alembic_version" in tables
    # Drift guard: migrations must produce exactly what the models declare.
    assert tables == {"alembic_version"} | {
        table.name for table in Base.metadata.sorted_tables
    }


def test_upgrade_then_downgrade_is_clean(tmp_path):
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'downgrade.db').as_posix()}"
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    # Alembic keeps its bookkeeping table (stamped empty) after downgrade.
    with engine.connect() as conn:
        stamped = conn.execute(sa.text("SELECT version_num FROM alembic_version")).fetchall()
    engine.dispose()

    assert tables == {"alembic_version"}
    assert stamped == []


def test_migrated_columns_match_model(tmp_path):
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'columns.db').as_posix()}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")

    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("users")}
    engine.dispose()

    expected = {col.name for col in Base.metadata.tables["users"].columns}
    assert columns == expected
