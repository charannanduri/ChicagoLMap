"""
Infer actual arrival times from consecutive arrival_snapshots.

Strategy
--------
For a given (run_number, station_id) pair, scan snapshots in chronological
order.  A train is considered to have arrived when:

  1. Its ETA reaches ≤ 0 seconds in the predictions, OR
  2. The run number disappears from predictions for that station after having
     been ≤ 60 s away in the previous snapshot.

The inferred actual_arrival_time is the last CTA arr_t value before the train
vanished, which is typically accurate to within the poll interval (≈25 s).

A GTFS schedule match is attempted by finding the stop_time row for a
service_id active on the service day, for the Red or Blue route, stopping at
this station within a ±30-minute window around the inferred arrival.

Run periodically (e.g. every 5 minutes):
    python -m backend.etl.arrival_inference
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytz
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db.init_db import init_db
from backend.db.models import ActualArrival, ArrivalSnapshot, GtfsCalendar, GtfsStopTime
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

_TZ = pytz.timezone("America/Chicago")
_LOOKBACK_HOURS = 2   # only process snapshots from last N hours
_ETA_THRESHOLD_S = 60  # treat run as "arrived" when ETA ≤ this
_DISAPPEAR_THRESHOLD_S = 360  # also treat as arrived if run vanishes within this window
_MATCH_WINDOW_MIN = 30  # ± minutes for GTFS schedule matching


def _hhmmss_to_seconds(s: str) -> int:
    """Parse HH:MM:SS (possibly >23:59:59) to total seconds since midnight."""
    parts = s.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def _active_service_ids(db: Session, date: datetime) -> set[str]:
    """Return GTFS service_ids active on the given date."""
    dow = date.strftime("%A").lower()  # e.g. "monday"
    date_str = date.strftime("%Y%m%d")

    calendar_ids: set[str] = {
        row.service_id
        for row in db.query(GtfsCalendar)
        if getattr(row, dow) and row.start_date <= date_str <= row.end_date
    }

    added_raw = db.execute(
        text("SELECT service_id FROM gtfs_calendar_dates WHERE date=:d AND exception_type=1"),
        {"d": date_str},
    ).fetchall()
    removed_raw = db.execute(
        text("SELECT service_id FROM gtfs_calendar_dates WHERE date=:d AND exception_type=2"),
        {"d": date_str},
    ).fetchall()

    result = (calendar_ids | {r[0] for r in added_raw}) - {r[0] for r in removed_raw}
    return result


def _find_scheduled_arrival(
    db: Session,
    station_id: str,
    actual_dt: datetime,
    service_ids: set[str],
    run_number: str,
) -> datetime | None:
    """
    Find the GTFS scheduled arrival for the station closest in time to actual_dt.

    We query stop_times whose arrival_time (as seconds since midnight) falls
    within _MATCH_WINDOW_MIN minutes of actual_dt's time-of-day, for a trip
    whose service_id is active today.
    """
    if not service_ids:
        return None

    local_dt = actual_dt.astimezone(_TZ)
    sod_s = local_dt.hour * 3600 + local_dt.minute * 60 + local_dt.second
    window_s = _MATCH_WINDOW_MIN * 60

    # station_id is the CTA mapid (parent station, e.g. "40900").
    # GTFS stop_times references platform-level stop_ids (e.g. "30173") whose
    # parent_station column equals the mapid. We must join through gtfs_stops.
    stop_time_rows = (
        db.execute(
            text(
                """
                SELECT st.arrival_time, st.trip_id
                FROM gtfs_stop_times st
                JOIN gtfs_stops   gs ON gs.stop_id  = st.stop_id
                JOIN gtfs_trips    t ON t.trip_id   = st.trip_id
                WHERE gs.parent_station = :station_id
                  AND t.service_id = ANY(:sids)
                """
            ),
            {"station_id": station_id, "sids": list(service_ids)},
        ).fetchall()
    )

    best_dt: datetime | None = None
    best_diff = float("inf")
    for arr_time_str, _trip_id in stop_time_rows:
        if not arr_time_str:
            continue
        try:
            sched_s = _hhmmss_to_seconds(arr_time_str)
        except (ValueError, IndexError):
            continue
        diff = abs(sched_s - sod_s)
        if diff < window_s and diff < best_diff:
            best_diff = diff
            base = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            best_dt = _TZ.localize(
                base.replace(tzinfo=None) + timedelta(seconds=sched_s)
            )
    return best_dt


def infer_arrivals(lookback_hours: int | None = _LOOKBACK_HOURS) -> int:
    """
    Scan recent snapshots and write new ActualArrival rows.

    Pass lookback_hours=None to process all data (full reprocess).
    Returns the number of new rows inserted.
    """
    since = (
        datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        if lookback_hours is not None
        else datetime.min.replace(tzinfo=timezone.utc)
    )
    inserted = 0

    with SessionLocal() as db:
        rows = (
            db.query(ArrivalSnapshot)
            .filter(ArrivalSnapshot.snapshot_time >= since)
            .order_by(ArrivalSnapshot.run_number, ArrivalSnapshot.station_id, ArrivalSnapshot.snapshot_time)
            .all()
        )

        # Group by (run_number, station_id)
        groups: dict[tuple[str, str], list[ArrivalSnapshot]] = {}
        for row in rows:
            key = (row.run_number or "", row.station_id or "")
            groups.setdefault(key, []).append(row)

        for (run_number, station_id), snaps in groups.items():
            if not run_number or not station_id:
                continue

            snaps.sort(key=lambda s: s.snapshot_time)

            # Find the last snapshot where arr_t is still in the future and
            # the one after where the run disappears or ETA ≤ threshold.
            arrival_snap: ArrivalSnapshot | None = None
            for i, snap in enumerate(snaps):
                if snap.arr_t is None:
                    continue
                eta_s = (snap.arr_t - snap.snapshot_time).total_seconds()
                if eta_s <= _ETA_THRESHOLD_S:
                    arrival_snap = snap
                    break
                # Check if run disappears in the next snapshot.
                # Use _DISAPPEAR_THRESHOLD_S (360s) rather than 120s so that
                # trains predicted 2–5 min away at poll time are still caught
                # when the 5-minute GitHub Actions cron misses the ≤60s window.
                if i + 1 < len(snaps):
                    next_snaps_for_key = [
                        s for s in snaps[i + 1:]
                        if s.station_id == station_id
                    ]
                    if not next_snaps_for_key and eta_s < _DISAPPEAR_THRESHOLD_S:
                        arrival_snap = snap
                        break

            if arrival_snap is None:
                continue

            actual_dt = arrival_snap.arr_t
            # Build service_ids for the arrival date
            service_ids = _active_service_ids(db, actual_dt)
            scheduled_dt = _find_scheduled_arrival(db, station_id, actual_dt, service_ids, run_number)

            delay_min = None
            if scheduled_dt is not None:
                delay_min = round(
                    (actual_dt - scheduled_dt).total_seconds() / 60, 2
                )

            # Skip if already exists
            exists = (
                db.query(ActualArrival)
                .filter(
                    ActualArrival.run_number == run_number,
                    ActualArrival.station_id == station_id,
                    ActualArrival.actual_arrival_time == actual_dt,
                )
                .first()
            )
            if exists:
                continue

            db.add(
                ActualArrival(
                    run_number=run_number,
                    route=arrival_snap.route or "",
                    direction=arrival_snap.direction or "",
                    station_id=station_id,
                    scheduled_arrival_time=scheduled_dt,
                    actual_arrival_time=actual_dt,
                    delay_minutes=delay_min,
                    source_confidence=0.9 if scheduled_dt else 0.5,
                )
            )
            inserted += 1

        db.commit()

    logger.info("Inferred %d new actual arrivals", inserted)
    return inserted


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="Process all historical data, not just the last 2 hours")
    p.add_argument("--hours", type=int, default=None)
    args = p.parse_args()
    init_db()
    hours = None if args.all else (args.hours or _LOOKBACK_HOURS)
    infer_arrivals(lookback_hours=hours)
