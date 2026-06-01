"""
Download the CTA GTFS zip and load it into the database.

The loader is idempotent: it truncates and reloads GTFS tables on each run,
which is safe because GTFS data is static / slowly changing.

Run directly:
    python -m backend.gtfs.loader
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from pathlib import Path

import httpx

from backend.config import get_settings
from backend.db.init_db import init_db
from backend.db.models import (
    GtfsCalendar,
    GtfsCalendarDate,
    GtfsRoute,
    GtfsStop,
    GtfsStopTime,
    GtfsTrip,
)
from backend.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

settings = get_settings()

# Load all CTA rail routes from GTFS
_TARGET_ROUTES = {"Red", "Blue", "G", "Brn", "Org", "P", "Pink", "Y"}


def _download_gtfs(url: str) -> bytes:
    logger.info("Downloading GTFS from %s", url)
    with httpx.Client(timeout=120) as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
    logger.info("GTFS download complete — %d bytes", len(resp.content))
    return resp.content


def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    """Read a file from the zip and return its rows as list-of-dicts."""
    with zf.open(name) as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        return list(reader)


def _bool(val: str | None) -> bool:
    return str(val).strip() == "1"


def load_gtfs(zip_bytes: bytes | None = None) -> None:
    """
    Load CTA GTFS data into Postgres.

    Pass zip_bytes to avoid re-downloading (useful in tests / CI).
    """
    init_db()

    if zip_bytes is None:
        zip_bytes = _download_gtfs(settings.gtfs_url)

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = set(zf.namelist())

    with SessionLocal() as db:
        # ---- routes -------------------------------------------------------
        if "routes.txt" in names:
            rows = _read_csv(zf, "routes.txt")
            db.query(GtfsRoute).delete()
            for r in rows:
                if r.get("route_id") not in _TARGET_ROUTES and r.get("route_short_name") not in _TARGET_ROUTES:
                    # Accept by route_id or by short name
                    continue
                db.add(
                    GtfsRoute(
                        route_id=r["route_id"],
                        route_short_name=r.get("route_short_name"),
                        route_long_name=r.get("route_long_name"),
                        route_type=int(r.get("route_type") or 0),
                        route_color=r.get("route_color"),
                    )
                )
            db.flush()
            logger.info("Loaded routes")

        # ---- stops --------------------------------------------------------
        if "stops.txt" in names:
            rows = _read_csv(zf, "stops.txt")
            db.query(GtfsStop).delete()
            for r in rows:
                db.add(
                    GtfsStop(
                        stop_id=r["stop_id"],
                        stop_name=r.get("stop_name"),
                        stop_lat=r.get("stop_lat") or None,
                        stop_lon=r.get("stop_lon") or None,
                        location_type=int(r.get("location_type") or 0),
                        parent_station=r.get("parent_station") or None,
                        wheelchair_boarding=int(r.get("wheelchair_boarding") or 0),
                    )
                )
            db.flush()
            logger.info("Loaded %d stops", len(rows))

        # ---- trips (only Red + Blue) --------------------------------------
        if "trips.txt" in names:
            valid_route_ids: set[str] = {
                row.route_id for row in db.query(GtfsRoute.route_id)
            }
            rows = _read_csv(zf, "trips.txt")
            db.query(GtfsTrip).delete()
            trip_ids: set[str] = set()
            for r in rows:
                if r.get("route_id") not in valid_route_ids:
                    continue
                trip_ids.add(r["trip_id"])
                db.add(
                    GtfsTrip(
                        trip_id=r["trip_id"],
                        route_id=r["route_id"],
                        service_id=r.get("service_id", ""),
                        direction_id=int(r.get("direction_id") or 0),
                        trip_headsign=r.get("trip_headsign"),
                        shape_id=r.get("shape_id"),
                    )
                )
            db.flush()
            logger.info("Loaded %d trips", len(trip_ids))

        # ---- stop_times (only trips loaded above) -------------------------
        if "stop_times.txt" in names:
            rows = _read_csv(zf, "stop_times.txt")
            db.query(GtfsStopTime).delete()
            batch: list[GtfsStopTime] = []
            for r in rows:
                if r.get("trip_id") not in trip_ids:
                    continue
                batch.append(
                    GtfsStopTime(
                        trip_id=r["trip_id"],
                        arrival_time=r.get("arrival_time"),
                        departure_time=r.get("departure_time"),
                        stop_id=r["stop_id"],
                        stop_sequence=int(r.get("stop_sequence") or 0),
                    )
                )
                if len(batch) >= 5000:
                    db.bulk_save_objects(batch)
                    db.flush()
                    batch = []
            if batch:
                db.bulk_save_objects(batch)
            db.flush()
            logger.info("Loaded stop_times")

        # ---- calendar -----------------------------------------------------
        if "calendar.txt" in names:
            rows = _read_csv(zf, "calendar.txt")
            db.query(GtfsCalendar).delete()
            for r in rows:
                db.add(
                    GtfsCalendar(
                        service_id=r["service_id"],
                        monday=_bool(r.get("monday")),
                        tuesday=_bool(r.get("tuesday")),
                        wednesday=_bool(r.get("wednesday")),
                        thursday=_bool(r.get("thursday")),
                        friday=_bool(r.get("friday")),
                        saturday=_bool(r.get("saturday")),
                        sunday=_bool(r.get("sunday")),
                        start_date=r.get("start_date"),
                        end_date=r.get("end_date"),
                    )
                )
            db.flush()
            logger.info("Loaded calendar")

        if "calendar_dates.txt" in names:
            rows = _read_csv(zf, "calendar_dates.txt")
            db.query(GtfsCalendarDate).delete()
            for r in rows:
                db.add(
                    GtfsCalendarDate(
                        service_id=r["service_id"],
                        date=r["date"],
                        exception_type=int(r.get("exception_type") or 1),
                    )
                )
            db.flush()
            logger.info("Loaded calendar_dates")

        db.commit()
    logger.info("GTFS load complete.")


if __name__ == "__main__":
    load_gtfs()
