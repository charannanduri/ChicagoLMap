"""
Polling service — runs continuously, writing arrival snapshots and
train positions to the database every POLL_INTERVAL_SECONDS.

Run as a module:
    python -m backend.collector.service
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

from backend.collector.cta_client import CtaTrainClient
from backend.config import get_settings
from backend.db.init_db import init_db
from backend.db.models import ArrivalSnapshot, TrainPosition
from backend.db.session import SessionLocal
from backend.stations import ALL_STATIONS, stations_for_route

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()


def _poll_arrivals(client: CtaTrainClient) -> None:
    """Poll ttarrivals for every Red + Blue station and persist snapshots."""
    now = datetime.now(timezone.utc)
    rows: list[ArrivalSnapshot] = []

    for station in ALL_STATIONS:
        etas = client.get_arrivals(station.mapid, max_results=10)
        for eta in etas:
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

    if rows:
        with SessionLocal() as db:
            db.add_all(rows)
            db.commit()
        logger.info("Persisted %d arrival snapshots at %s", len(rows), now.isoformat())
    else:
        logger.warning("No arrival snapshots collected at %s", now.isoformat())


def _poll_positions(client: CtaTrainClient) -> None:
    """Poll ttpositions for Red and Blue lines and persist positions."""
    now = datetime.now(timezone.utc)
    rows: list[TrainPosition] = []

    for route in ("Red", "Blue"):
        positions = client.get_positions(route)
        for p in positions:
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

    if rows:
        with SessionLocal() as db:
            db.add_all(rows)
            db.commit()
        logger.info("Persisted %d train positions at %s", len(rows), now.isoformat())


def run() -> None:
    logger.info("Initialising database…")
    init_db()

    key = settings.cta_train_tracker_key
    if not key:
        raise RuntimeError("CTA_TRAIN_TRACKER_KEY is not set")

    interval = settings.poll_interval_seconds
    logger.info("Starting collector — polling every %ss", interval)

    scheduler = BlockingScheduler()
    client = CtaTrainClient(key)

    scheduler.add_job(
        _poll_arrivals,
        "interval",
        seconds=interval,
        args=[client],
        id="arrivals",
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        _poll_positions,
        "interval",
        seconds=interval,
        args=[client],
        id="positions",
        next_run_time=datetime.now(timezone.utc),
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Collector stopped.")
    finally:
        client.close()


if __name__ == "__main__":
    run()
