"""
One-time backfill: re-parse raw_json to populate arr_t / prdt in
arrival_snapshots rows where they are NULL.

This fixes data collected before the cta_client._parse_cta_dt bug was patched
(it only handled YYYYMMDD HH:MM:SS but the JSON API returns ISO-8601).

Strategy: all affected rows have ISO-8601 timestamps inside raw_json
(e.g. "arrT": "2026-05-30T22:12:45").  PostgreSQL can cast that string
directly to TIMESTAMP — so we do the entire operation in a single SQL
UPDATE rather than 45k round-trips.

Safe to run repeatedly — only touches rows where arr_t IS NULL.

Run:
    python -m backend.etl.backfill_timestamps
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from backend.db.init_db import init_db
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def backfill(dry_run: bool = False) -> int:
    init_db()

    with SessionLocal() as db:
        pending = db.execute(
            text("SELECT COUNT(*) FROM arrival_snapshots WHERE arr_t IS NULL AND raw_json IS NOT NULL")
        ).scalar()
        logger.info("%d rows need backfill", pending)

        if pending == 0:
            logger.info("Nothing to do.")
            return 0

        if dry_run:
            logger.info("Dry run — no changes written.")
            return pending

        # ISO-8601 timestamps stored in raw_json can be cast directly by
        # PostgreSQL.  We convert to Chicago local time by interpreting the
        # naive timestamp as being in America/Chicago and then converting to UTC
        # for storage.  The AT TIME ZONE expression does exactly that.
        result = db.execute(
            text(
                """
                UPDATE arrival_snapshots
                SET
                    arr_t = ((raw_json::jsonb->>'arrT')::timestamp
                             AT TIME ZONE 'America/Chicago'),
                    prdt  = CASE
                        WHEN raw_json::jsonb->>'prdt' IS NOT NULL
                        THEN ((raw_json::jsonb->>'prdt')::timestamp
                              AT TIME ZONE 'America/Chicago')
                        ELSE NULL
                    END
                WHERE arr_t IS NULL
                  AND raw_json IS NOT NULL
                  AND (raw_json::jsonb->>'arrT') IS NOT NULL
                """
            )
        )
        updated = result.rowcount
        db.commit()

    logger.info("Backfill complete — updated %d rows", updated)
    return updated


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    backfill(dry_run=args.dry_run)
