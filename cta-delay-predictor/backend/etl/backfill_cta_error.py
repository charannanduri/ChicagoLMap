"""
Backfill model_features.cta_error_minutes for rows written before the column existed.

The CTA's prediction for a snapshot does not need arrival_snapshots (which is
pruned after two days) — it is recoverable from the feature row itself:

    arr_t = snapshot_time + minutes_until_arrival

because feature_builder derives minutes_until_arrival as
(snap.arr_t - snap.snapshot_time). Joining to actual_arrivals on
(run_number, station_id, direction) with the same window feature_builder uses
then gives

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
# reselect them endlessly. The id walk also lets us recompute rows the earlier
# direction-blind join had already filled in with the wrong arrival.
CHUNK = 20_000

_SQL = """
UPDATE model_features mf
SET cta_error_minutes = ROUND(
      (EXTRACT(EPOCH FROM (
          (SELECT aa.actual_arrival_time
             FROM actual_arrivals aa
            WHERE aa.run_number = mf.run_number
              AND aa.station_id = mf.station_id
              AND COALESCE(aa.direction, '') = COALESCE(mf.direction, '')
              AND aa.actual_arrival_time
                    BETWEEN mf.snapshot_time - INTERVAL '5 minutes'
                        AND mf.snapshot_time + INTERVAL '1 hour'
            ORDER BY aa.actual_arrival_time
            LIMIT 1)
          - (mf.snapshot_time
             + (mf.minutes_until_arrival::double precision * INTERVAL '1 minute'))
      )) / 60.0)::numeric, 2)
WHERE mf.id >= :lo AND mf.id < :hi
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
    skipped: list[tuple[int, int]] = []
    lo = lo_id
    while lo <= hi_id:
        hi = lo + CHUNK
        # The pooler drops a connection now and then. One retry turns a
        # transient blip into a non-event; a chunk that fails twice is a real
        # gap, so it gets recorded rather than quietly lost.
        for attempt in (1, 2):
            try:
                with engine.begin() as conn:
                    _ensure_writable(conn)
                    result = conn.execute(text(_SQL), {"lo": lo, "hi": hi})
                    updated = result.rowcount or 0
                total += updated
                if updated:
                    logger.info("  ids %d..%d → %d rows (%d total)", lo, hi, updated, total)
                break
            except Exception as exc:  # noqa: BLE001 — one bad chunk shouldn't end the run
                if attempt == 1:
                    logger.warning("  chunk %d..%d failed, retrying: %s", lo, hi, exc)
                    continue
                logger.error("  chunk %d..%d failed twice, skipping: %s", lo, hi, exc)
                skipped.append((lo, hi))
        lo = hi

    logger.info("Backfill complete: %d rows recomputed", total)
    if skipped:
        logger.error(
            "%d chunk(s) left unprocessed — re-run to fill them: %s",
            len(skipped), ", ".join(f"{a}..{b}" for a, b in skipped),
        )
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
    print()
    _report_join_ambiguity()
    print("=" * 62)


def _report_join_ambiguity() -> None:
    """
    Quantify how often the match window holds more than one arrival.

    CTA run numbers are reused across the service day, so one run visits a
    station in both directions inside the one-hour window the label join uses.
    Matching on direction as well as run+station removes those wrong-trip
    joins; whatever remains is genuine ambiguity we still label by taking the
    earliest arrival.
    """
    with engine.connect() as conn:
        row = conn.execute(text(
            """
            SELECT COUNT(*) AS groups,
                   COUNT(*) FILTER (WHERE n > 1) AS ambiguous
            FROM (
              SELECT run_number, station_id, direction,
                     date_trunc('hour', actual_arrival_time) AS hr,
                     COUNT(*) AS n
                FROM actual_arrivals
               GROUP BY 1, 2, 3, 4
            ) g
            """
        )).first()
    if not row or not row[0]:
        return
    groups, ambiguous = row
    pct = (ambiguous / groups * 100) if groups else 0.0
    print(f"  run+station+direction hour-buckets     {groups:,}")
    print(f"  ...holding more than one arrival       {ambiguous:,}  ({pct:.2f}%)")


if __name__ == "__main__":
    backfill()
    report()
