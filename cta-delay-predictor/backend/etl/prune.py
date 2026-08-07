"""
Delete the oldest append-only rows so the database stays within its storage
limit. Runs at the end of each collection job.

Why these windows:
  * arrival_snapshots — the space hog (a raw JSON blob per row). Only the last
    couple of hours are needed for arrival inference, so 7 days is generous.
  * train_positions — only powers the live map; nothing reads old rows.
  * model_features / actual_arrivals — the training set and its labels, so we
    keep a long window (the weekly retrain learns from these).

Best-effort and non-fatal: if the database is read-only (e.g. already over
quota) the deletes are skipped with a warning rather than failing the job.

Run as:
    python -m backend.etl.prune
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from backend.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# (table, time column, days to keep)
_RETENTION: list[tuple[str, str, int]] = [
    ("arrival_snapshots", "snapshot_time", 7),
    ("train_positions", "snapshot_time", 7),
    ("model_features", "snapshot_time", 120),
    ("actual_arrivals", "actual_arrival_time", 180),
]


def prune() -> int:
    """Delete rows older than each table's retention window. Returns rows deleted."""
    now = datetime.now(timezone.utc)
    total = 0
    for table, column, days in _RETENTION:
        cutoff = now - timedelta(days=days)
        try:
            with engine.begin() as conn:
                result = conn.execute(
                    text(f"DELETE FROM {table} WHERE {column} < :cutoff"),
                    {"cutoff": cutoff},
                )
                deleted = result.rowcount or 0
                total += deleted
                logger.info("Pruned %d rows from %s (older than %d days)", deleted, table, days)
        except Exception as exc:  # noqa: BLE001 — never fail the job over pruning
            logger.warning("Prune of %s skipped (%s)", table, exc)
    logger.info("Prune complete: %d rows deleted", total)
    return total


if __name__ == "__main__":
    prune()
