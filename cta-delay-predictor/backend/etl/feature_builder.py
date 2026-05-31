"""
Build model_features rows from arrival_snapshots + actual_arrivals.

For each snapshot record we compute the full feature vector.  When the
corresponding actual_arrival exists we attach delay_minutes and delay_status
(making it a labelled training example).  Otherwise the row is a live
prediction candidate.

Run periodically (e.g. every 5 minutes):
    python -m backend.etl.feature_builder
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytz
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db.init_db import init_db
from backend.db.models import ActualArrival, ArrivalSnapshot, ModelFeature
from backend.db.session import SessionLocal
from backend.stations import get_station

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

_TZ = pytz.timezone("America/Chicago")
_LOOKBACK_HOURS = 2


def _delay_status(delay_min: float | None) -> str | None:
    if delay_min is None:
        return None
    if delay_min < -1.0:
        return "ahead"
    if delay_min <= 2.0:
        return "on_time"
    return "behind"


def _is_peak_am(local_dt: datetime) -> bool:
    return local_dt.weekday() < 5 and 7 <= local_dt.hour < 9


def _is_peak_pm(local_dt: datetime) -> bool:
    return local_dt.weekday() < 5 and 16 <= local_dt.hour < 19


def build_features(lookback_hours: int | None = _LOOKBACK_HOURS) -> int:
    since = (
        datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        if lookback_hours is not None
        else datetime.min.replace(tzinfo=timezone.utc)
    )
    inserted = 0

    with SessionLocal() as db:
        snaps = (
            db.query(ArrivalSnapshot)
            .filter(ArrivalSnapshot.snapshot_time >= since)
            .order_by(ArrivalSnapshot.run_number, ArrivalSnapshot.station_id, ArrivalSnapshot.snapshot_time)
            .all()
        )

        # Headway lookup: (snapshot_time, station_id, direction) → sorted arr_t list
        headway_lookup: dict[tuple, list] = {}
        for snap in snaps:
            if snap.arr_t is not None:
                key = (snap.snapshot_time, snap.station_id, snap.direction or "")
                headway_lookup.setdefault(key, []).append(snap.arr_t)
        for key in headway_lookup:
            headway_lookup[key].sort()

        # Build previous-ETA lookup: (run_number, station_id) → [arr_t_minutes, ...]
        history: dict[tuple[str, str], list[float]] = {}

        for snap in snaps:
            run = snap.run_number or ""
            station = snap.station_id or ""
            key = (run, station)

            if snap.arr_t is None or snap.prdt is None:
                continue

            minutes_until = max(
                0.0,
                (snap.arr_t - snap.snapshot_time).total_seconds() / 60,
            )

            prev_etas = history.get(key, [])
            eta_delta_1 = None
            eta_delta_2 = None
            if len(prev_etas) >= 1:
                eta_delta_1 = round(minutes_until - prev_etas[-1], 3)
            if len(prev_etas) >= 2:
                eta_delta_2 = round(minutes_until - prev_etas[-2], 3)
            history[key] = (prev_etas + [minutes_until])[-3:]

            local_dt = snap.snapshot_time.astimezone(_TZ)
            station_obj = get_station(int(station)) if station.isdigit() else None

            # Look up actual arrival for this run+station
            actual: ActualArrival | None = (
                db.query(ActualArrival)
                .filter(
                    ActualArrival.run_number == run,
                    ActualArrival.station_id == station,
                    ActualArrival.actual_arrival_time >= snap.snapshot_time - timedelta(minutes=5),
                    ActualArrival.actual_arrival_time <= snap.snapshot_time + timedelta(hours=1),
                )
                .order_by(ActualArrival.actual_arrival_time)
                .first()
            )

            delay_min = float(actual.delay_minutes) if actual and actual.delay_minutes is not None else None
            status = _delay_status(delay_min)

            # Skip duplicate rows
            exists = (
                db.query(ModelFeature)
                .filter(
                    ModelFeature.run_number == run,
                    ModelFeature.station_id == station,
                    ModelFeature.snapshot_time == snap.snapshot_time,
                )
                .first()
            )
            if exists:
                continue

            direction_code = int(snap.direction) if snap.direction and snap.direction.isdigit() else None

            # Headway from sorted arr_t list for this snapshot+station+direction
            hw_before: float | None = None
            hw_after: float | None = None
            hw_key = (snap.snapshot_time, station, snap.direction or "")
            arr_ts = headway_lookup.get(hw_key, [])
            if snap.arr_t in arr_ts:
                idx = arr_ts.index(snap.arr_t)
                if idx > 0:
                    hw_before = round((snap.arr_t - arr_ts[idx - 1]).total_seconds() / 60, 2)
                if idx < len(arr_ts) - 1:
                    hw_after = round((arr_ts[idx + 1] - snap.arr_t).total_seconds() / 60, 2)

            db.add(
                ModelFeature(
                    run_number=run,
                    route=snap.route or "",
                    direction=snap.direction or "",
                    station_id=station,
                    station_name=station_obj.name if station_obj else None,
                    snapshot_time=snap.snapshot_time,
                    stop_sequence=station_obj.stop_sequence if station_obj else None,
                    is_red_line=(snap.route or "").lower() == "red",
                    is_blue_line=(snap.route or "").lower() == "blue",
                    direction_code=direction_code,
                    hour_of_day=local_dt.hour,
                    day_of_week=local_dt.weekday(),
                    month=local_dt.month,
                    is_weekend=local_dt.weekday() >= 5,
                    is_peak_am=_is_peak_am(local_dt),
                    is_peak_pm=_is_peak_pm(local_dt),
                    minutes_until_arrival=round(minutes_until, 3),
                    is_scheduled=snap.is_scheduled,
                    is_delayed_flag=snap.is_delayed,
                    is_faulty_flag=snap.is_faulty,
                    time_since_last_update_sec=round(
                        (snap.snapshot_time - snap.prdt).total_seconds(), 2
                    ) if snap.prdt else None,
                    eta_delta_1_min=eta_delta_1,
                    eta_delta_2_min=eta_delta_2,
                    headway_before_min=hw_before,
                    headway_after_min=hw_after,
                    delay_minutes=delay_min,
                    delay_status=status,
                )
            )
            inserted += 1

        db.commit()

    logger.info("Built %d new model_features rows", inserted)
    return inserted


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="Process all historical data")
    p.add_argument("--hours", type=int, default=None)
    args = p.parse_args()
    init_db()
    hours = None if args.all else (args.hours or _LOOKBACK_HOURS)
    build_features(lookback_hours=hours)
