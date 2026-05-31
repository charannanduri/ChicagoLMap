"""
One-time backfill: re-parse raw_json to populate arr_t / prdt in
arrival_snapshots rows where they are NULL.

This fixes data collected before the cta_client._parse_cta_dt bug was patched
(it only handled YYYYMMDD HH:MM:SS but the JSON API returns ISO-8601).

Safe to run repeatedly — skips rows that already have arr_t set.

Run:
    python -m backend.etl.backfill_timestamps
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import pytz
from sqlalchemy import text

from backend.db.init_db import init_db
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

_TZ = pytz.timezone("America/Chicago")
_BATCH = 5000


def _parse(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y%m%d %H:%M:%S"):
        try:
            return _TZ.localize(datetime.strptime(raw, fmt))
        except ValueError:
            continue
    return None


def backfill(dry_run: bool = False) -> int:
    init_db()
    updated = 0

    with SessionLocal() as db:
        # Count rows that need fixing
        total = db.execute(
            text("SELECT COUNT(*) FROM arrival_snapshots WHERE arr_t IS NULL AND raw_json IS NOT NULL")
        ).scalar()
        logger.info("%d rows need backfill", total)

        if total == 0:
            logger.info("Nothing to do.")
            return 0

        offset = 0
        while True:
            rows = db.execute(
                text(
                    "SELECT id, raw_json FROM arrival_snapshots "
                    "WHERE arr_t IS NULL AND raw_json IS NOT NULL "
                    "ORDER BY id LIMIT :lim OFFSET :off"
                ),
                {"lim": _BATCH, "off": offset},
            ).fetchall()

            if not rows:
                break

            for row_id, raw_json_str in rows:
                try:
                    payload = json.loads(raw_json_str)
                except (json.JSONDecodeError, TypeError):
                    continue

                arr_t = _parse(payload.get("arrT"))
                prdt = _parse(payload.get("prdt"))

                if arr_t is None:
                    continue  # can't fix without a valid timestamp

                if not dry_run:
                    db.execute(
                        text(
                            "UPDATE arrival_snapshots "
                            "SET arr_t = :arr_t, prdt = :prdt "
                            "WHERE id = :id"
                        ),
                        {"arr_t": arr_t, "prdt": prdt, "id": row_id},
                    )
                updated += 1

            if not dry_run:
                db.commit()

            offset += _BATCH
            logger.info("Processed %d / %d rows (updated %d so far)", offset, total, updated)

    logger.info("Backfill complete — updated %d rows", updated)
    return updated


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    backfill(dry_run=args.dry_run)
