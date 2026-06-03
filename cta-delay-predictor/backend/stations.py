"""
Static registry of CTA L parent stations (mapid = CTA parent station ID).

The authoritative source is the CTA GTFS feed loaded into gtfs_stops.
load_gtfs_stations() queries that table and returns all parent stations for
all 8 lines at runtime. The hardcoded RED_LINE / BLUE_LINE lists serve as a
fallback when the DB is unavailable (e.g. first cold start before GTFS load).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Station:
    mapid: int
    name: str
    route: str = ""         # "Red" | "Blue" | "G" | … — empty for GTFS-loaded entries
    stop_sequence: int = 0  # approximate order; 0 for GTFS-loaded entries
    branch: str = ""        # "ohare" | "forest_park" | ""


RED_LINE: list[Station] = [
    Station(40900, "Howard",           "Red",  1),
    Station(41190, "Jarvis",           "Red",  2),
    Station(40100, "Morse",            "Red",  3),
    Station(41300, "Loyola",           "Red",  4),
    Station(40760, "Granville",        "Red",  5),
    Station(40880, "Thorndale",        "Red",  6),
    Station(41380, "Bryn Mawr",        "Red",  7),
    Station(40340, "Berwyn",           "Red",  8),
    Station(41200, "Argyle",           "Red",  9),
    Station(40540, "Wilson",           "Red", 10),
    Station(40080, "Sheridan",         "Red", 11),
    Station(41420, "Addison",          "Red", 12),
    Station(41320, "Belmont",          "Red", 13),
    Station(41220, "Fullerton",        "Red", 14),
    Station(40650, "North/Clybourn",   "Red", 15),
    Station(40630, "Clark/Division",   "Red", 16),
    Station(41450, "Chicago",          "Red", 17),
    Station(40330, "Grand",            "Red", 18),
    Station(41660, "Lake",             "Red", 19),
    Station(41090, "Monroe",           "Red", 20),
    Station(40560, "Jackson",          "Red", 21),
    Station(41490, "Harrison",         "Red", 22),
    Station(41000, "Cermak-Chinatown", "Red", 23),
    Station(40190, "Sox-35th",         "Red", 24),
    Station(41230, "47th",             "Red", 25),
    Station(41170, "Garfield",         "Red", 26),
    Station(40910, "63rd",             "Red", 27),
    Station(40990, "69th",             "Red", 28),
    Station(40240, "79th",             "Red", 29),
    Station(41430, "87th",             "Red", 30),
    Station(40450, "95th/Dan Ryan",    "Red", 31),
]

BLUE_LINE: list[Station] = [
    # O'Hare branch
    Station(40890, "O'Hare",                    "Blue",  1, "ohare"),
    Station(40820, "Rosemont",                  "Blue",  2, "ohare"),
    Station(40230, "Cumberland",                "Blue",  3, "ohare"),
    Station(40750, "Harlem (O'Hare)",           "Blue",  4, "ohare"),
    Station(41280, "Jefferson Park",            "Blue",  5, "ohare"),
    Station(41330, "Montrose",                  "Blue",  6, "ohare"),
    Station(40550, "Irving Park",               "Blue",  7, "ohare"),
    Station(41240, "Addison",                   "Blue",  8, "ohare"),
    Station(40060, "Belmont",                   "Blue",  9, "ohare"),
    Station(41020, "Logan Square",              "Blue", 10, "ohare"),
    Station(40570, "California",                "Blue", 11, "ohare"),
    Station(40670, "Western (O'Hare)",          "Blue", 12, "ohare"),
    Station(40590, "Damen",                     "Blue", 13, "ohare"),
    # Shared trunk (Division through Jackson)
    Station(40320, "Division",                  "Blue", 14),
    Station(41410, "Chicago",                   "Blue", 15),
    Station(40490, "Grand",                     "Blue", 16),
    Station(40380, "Clark/Lake",                "Blue", 17),
    Station(40370, "Washington",                "Blue", 18),
    Station(40790, "Monroe",                    "Blue", 19),
    Station(41340, "Jackson",                   "Blue", 20),
    # Forest Park branch
    Station(40430, "LaSalle",                   "Blue", 21, "forest_park"),
    Station(40390, "Clinton",                   "Blue", 22, "forest_park"),
    Station(40350, "UIC-Halsted",               "Blue", 23, "forest_park"),
    Station(40470, "Racine",                    "Blue", 24, "forest_park"),
    Station(40810, "Illinois Medical District", "Blue", 25, "forest_park"),
    Station(40220, "Western (Forest Park)",     "Blue", 26, "forest_park"),
    Station(40250, "Kedzie-Homan",              "Blue", 27, "forest_park"),
    Station(40920, "Pulaski",                   "Blue", 28, "forest_park"),
    Station(40970, "Cicero",                    "Blue", 29, "forest_park"),
    Station(40010, "Austin",                    "Blue", 30, "forest_park"),
    Station(40180, "Oak Park",                  "Blue", 31, "forest_park"),
    Station(40980, "Harlem/Lake",               "Blue", 32, "forest_park"),
    Station(40390, "Forest Park",               "Blue", 33, "forest_park"),
]

ALL_STATIONS: list[Station] = RED_LINE + BLUE_LINE

_BY_MAPID: dict[int, Station] = {s.mapid: s for s in ALL_STATIONS}


def get_station(mapid: int) -> Station | None:
    return _BY_MAPID.get(mapid)


def stations_for_route(route: str) -> list[Station]:
    """Return ordered station list for a given route from the hardcoded registry."""
    return [s for s in ALL_STATIONS if s.route.lower() == route.lower()]


def load_gtfs_stations() -> list[Station]:
    """Return all parent stations from the GTFS data already in the DB.

    Queries gtfs_stops WHERE location_type = 1 (parent/station nodes).
    Falls back to the hardcoded ALL_STATIONS list if the DB is unavailable
    or GTFS has not been loaded yet.
    """
    try:
        from backend.db.models import GtfsStop
        from backend.db.session import SessionLocal

        with SessionLocal() as db:
            rows = db.query(GtfsStop).filter(GtfsStop.location_type == 1).all()
            if rows:
                stations: list[Station] = []
                for r in rows:
                    try:
                        stations.append(Station(mapid=int(r.stop_id), name=r.stop_name or ""))
                    except (ValueError, TypeError):
                        continue
                logger.info("Loaded %d parent stations from GTFS (all lines).", len(stations))
                return stations
    except Exception as exc:
        logger.warning("GTFS station load failed, falling back to hardcoded list: %s", exc)
    return ALL_STATIONS
