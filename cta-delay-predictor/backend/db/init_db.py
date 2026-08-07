"""Create all tables (idempotent) and apply lightweight schema migrations.

Migrations are applied **conditionally, non-fatally, and once per process**: we
check first with a read-only query and only issue DDL/DML when it's actually
needed. That keeps a database that's already migrated — or one that's
temporarily read-only (e.g. Supabase over its storage quota) — from erroring out
the whole collector on every cycle.
"""

import logging

from sqlalchemy import text

from backend.db.models import Base
from backend.db.session import engine

logger = logging.getLogger(__name__)

_migrations_applied = False


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
            LIMIT 1
            """
        ),
        {"t": table, "c": column},
    ).first()
    return row is not None


_ROUTE_CODE_BACKFILL = """
    UPDATE model_features SET route_code = CASE
        WHEN route = 'Red'  THEN 0
        WHEN route = 'Blue' THEN 1
        WHEN route = 'G'    THEN 2
        WHEN route = 'Brn'  THEN 3
        WHEN route = 'Org'  THEN 4
        WHEN route = 'P'    THEN 5
        WHEN route = 'Pink' THEN 6
        WHEN route = 'Y'    THEN 7
        ELSE -1
    END
    WHERE route_code IS NULL
"""


def _run_migrations() -> None:
    """Apply schema migrations only when the schema actually needs them.

    Best-effort: on a read-only database this does only SELECTs (the write
    branches are skipped once the migration has already been applied), and any
    unexpected failure is logged rather than raised so collection can proceed.
    """
    global _migrations_applied
    if _migrations_applied:
        return
    try:
        with engine.begin() as conn:
            if not _column_exists(conn, "model_features", "route_code"):
                conn.execute(text("ALTER TABLE model_features ADD COLUMN route_code INTEGER"))

            needs_backfill = conn.execute(
                text("SELECT 1 FROM model_features WHERE route_code IS NULL LIMIT 1")
            ).first() is not None
            if needs_backfill:
                conn.execute(text(_ROUTE_CODE_BACKFILL))
        _migrations_applied = True
    except Exception as exc:  # noqa: BLE001 — never let migrations kill collection
        logger.warning("Skipping schema migrations (%s)", exc)


def init_db() -> None:
    # create_all only emits CREATE TABLE for tables that don't exist yet, so on
    # an already-provisioned database it issues no DDL and is read-only-safe.
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Table creation skipped (%s)", exc)
    _run_migrations()
    logger.info("Database tables created / verified.")


if __name__ == "__main__":
    init_db()
