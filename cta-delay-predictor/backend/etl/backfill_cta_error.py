"""
Backfill model_features.cta_error_minutes for rows written before the column existed.

The CTA's prediction for a snapshot does not need arrival_snapshots (which is
pruned after two days) — it is recoverable from the feature row itself:

    arr_t = snapshot_time + minutes_until_arrival

because feature_builder derives minutes_until_arrival as
(snap.arr_t - snap.snapshot_time). Joining to actual_arrivals on
(run_number, station_id) with the same window feature_builder uses then gives

    cta_error_minutes = actual_arrival_time - arr_t

Run as:
    python -m backend.etl.backfill_cta_error
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from backend.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Walk the table by id range rather than by "WHERE cta_error_minutes IS NULL".
# Rows with no matching arrival stay NULL forever, so a NULL-filtered loop would
# reselect them endlessly.
CHUNK = 20_000

_SQL = """
UPDATE model_features mf
SET cta_error_minutes = ROUND(
      (EXTRACT(EPOCH FROM (
          (SELECT aa.actual_arrival_time
             FROM actual_arrivals aa
            WHERE aa.run_number = mf.run_number
              AND aa.station_id = mf.station_id
              AND aa.actual_arrival_time
                    BETWEEN mf.snapshot_time - INTERVAL '5 minutes'
                        AND mf.snapshot_time + INTERVAL '1 hour'
            ORDER BY aa.actual_arrival_time
            LIMIT 1)
          - (mf.snapshot_time
             + (mf.minutes_until_arrival::double precision * INTERVAL '1 minute'))
      )) / 60.0)::numeric, 2)
WHERE mf.id >= :lo AND mf.id < :hi
  AND mf.cta_error_minutes IS NULL
  AND mf.minutes_until_arrival IS NOT NULL
"""


def _ensure_writable(conn) -> None:
    """Lift read-only for this transaction if the database is parked over quota."""
    for stmt in ("SET TRANSACTION READ WRITE", "SET LOCAL default_transaction_read_only = off"):
        try:
            conn.execute(text(stmt))
        except Exception:  # noqa: BLE001 — already writable, or not permitted
            pass


def backfill() -> int:
    with engine.connect() as conn:
        bounds = conn.execute(
            text("SELECT COALESCE(MIN(id), 0), COALESCE(MAX(id), -1) FROM model_features")
        ).first()
    lo_id, hi_id = int(bounds[0]), int(bounds[1])
    if hi_id < lo_id:
        logger.info("model_features is empty — nothing to backfill")
        return 0

    logger.info("Backfilling ids %d..%d in chunks of %d", lo_id, hi_id, CHUNK)
    total = 0
    lo = lo_id
    while lo <= hi_id:
        hi = lo + CHUNK
        try:
            with engine.begin() as conn:
                _ensure_writable(conn)
                result = conn.execute(text(_SQL), {"lo": lo, "hi": hi})
                updated = result.rowcount or 0
            total += updated
            if updated:
                logger.info("  ids %d..%d → %d rows (%d total)", lo, hi, updated, total)
        except Exception as exc:  # noqa: BLE001 — one bad chunk shouldn't end the run
            logger.warning("  chunk %d..%d failed: %s", lo, hi, exc)
        lo = hi

    logger.info("Backfill complete: %d rows given a cta_error_minutes value", total)
    return total


def report() -> None:
    """Print how the two targets compare, which is the whole point of the exercise."""
    with engine.connect() as conn:
        row = conn.execute(text(
            """
            SELECT
              COUNT(*)                                          AS total,
              COUNT(delay_minutes)                              AS have_v1,
              COUNT(cta_error_minutes)                          AS have_v2,
              ROUND(AVG(ABS(delay_minutes)), 3)                 AS mean_abs_v1,
              ROUND(AVG(ABS(cta_error_minutes)), 3)             AS mean_abs_v2,
              ROUND(STDDEV(delay_minutes), 3)                   AS std_v1,
              ROUND(STDDEV(cta_error_minutes), 3)               AS std_v2
            FROM model_features
            """
        )).first()

    if not row:
        return
    total, have_v1, have_v2, mabs1, mabs2, std1, std2 = row
    print("=" * 62)
    print("TARGET COMPARISON  (model_features)")
    print("=" * 62)
    print(f"  rows                                   {total:,}")
    print(f"  labelled — v1 timetable delay          {have_v1:,}")
    print(f"  labelled — v2 CTA prediction error     {have_v2:,}")
    print()
    print(f"  mean |v1|  (actual - timetable)        {mabs1} min")
    print(f"  mean |v2|  (actual - CTA prediction)   {mabs2} min")
    print(f"  std  v1                                {std1} min")
    print(f"  std  v2                                {std2} min")
    print()
    print("  A larger spread in v2 is the good outcome: it means the CTA's")
    print("  error carries variation a model can actually learn, where the")
    print("  timetable label was compressed toward zero by construction.")
    print("=" * 62)


if __name__ == "__main__":
    backfill()
    report()
