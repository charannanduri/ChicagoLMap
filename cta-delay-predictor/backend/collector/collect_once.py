"""
One-shot collector — polls CTA API once and writes to the database.

Designed to be called by GitHub Actions on a cron schedule.
Run as:
    python -m backend.collector.collect_once
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.collector.cta_client import CtaTrainClient
from backend.config import get_settings
from backend.db.init_db import init_db
from backend.db.models import ArrivalSnapshot, TrainPosition
from backend.db.session import SessionLocal
from backend.stations import load_gtfs_stations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


_ALL_ROUTES = ("Red", "Blue", "G", "Brn", "Org", "P", "Pink", "Y")


def _collect_arrivals(client: CtaTrainClient, now: datetime) -> list[ArrivalSnapshot]:
    rows: list[ArrivalSnapshot] = []
    for station in load_gtfs_stations():
        for eta in client.get_arrivals(station.mapid, max_results=10):
            rows.append(
                ArrivalSnapshot(
                    snapshot_time=now,
                    station_id=str(eta["station_id"]),
                    stop_id=str(eta["stop_id"]),
                    route=str(eta["route"] or ""),
                    direction=str(eta["direction"] or ""),
                    run_number=str(eta["run_number"] or ""),
                    destination=str(eta["destination"] or ""),
                    prdt=eta["prdt"],
                    arr_t=eta["arr_t"],
                    is_scheduled=eta["is_scheduled"],
                    is_delayed=eta["is_delayed"],
                    is_faulty=eta["is_faulty"],
                    raw_json=eta["raw"],
                )
            )
    return rows


def _collect_positions(client: CtaTrainClient, now: datetime) -> list[TrainPosition]:
    rows: list[TrainPosition] = []
    for route in _ALL_ROUTES:
        for p in client.get_positions(route):
            rows.append(
                TrainPosition(
                    snapshot_time=now,
                    run_number=str(p["run_number"] or ""),
                    route=str(p["route"] or ""),
                    direction=str(p["direction"] or ""),
                    lat=p["lat"],
                    lon=p["lon"],
                    heading=p["heading"],
                    next_station_id=str(p["next_station_id"] or ""),
                    next_station_name=str(p["next_station_name"] or ""),
                    is_approaching=p["is_approaching"],
                    is_delayed=p["is_delayed"],
                )
            )
    return rows


def main() -> None:
    settings = get_settings()
    if not settings.cta_train_tracker_key:
        raise RuntimeError("CTA_TRAIN_TRACKER_KEY is not set")

    logger.info("Initialising database…")
    init_db()

    now = datetime.now(timezone.utc)
    logger.info("Polling CTA API at %s", now.isoformat())

    with CtaTrainClient(settings.cta_train_tracker_key) as client:
        arrivals = _collect_arrivals(client, now)
        positions = _collect_positions(client, now)

    with SessionLocal() as db:
        db.add_all(arrivals)
        db.add_all(positions)
        db.commit()

    logger.info("Saved %d arrivals, %d positions", len(arrivals), len(positions))


if __name__ == "__main__":
    main()
