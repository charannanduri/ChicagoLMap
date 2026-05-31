"""
CTA Train Tracker JSON client.

Uses outputType=JSON so we don't need XML parsing. All timestamps from
the CTA API are naive local Chicago time; we attach America/Chicago tzinfo
before storing.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx
import pytz

logger = logging.getLogger(__name__)

_TZ = pytz.timezone("America/Chicago")
_BASE = "http://lapi.transitchicago.com/api/1.0"
_ARRIVALS_URL = f"{_BASE}/ttarrivals.aspx"
_POSITIONS_URL = f"{_BASE}/ttpositions.aspx"

_ROUTE_IDS = {
    "red": "Red",
    "blue": "Blue",
    "brn": "Brn",
    "brown": "Brn",
    "g": "G",
    "green": "G",
    "org": "Org",
    "orange": "Org",
    "p": "P",
    "purple": "P",
    "pink": "Pink",
    "pnk": "Pink",
    "y": "Y",
    "yellow": "Y",
}


def _parse_cta_dt(raw: str | None) -> datetime | None:
    """Parse CTA timestamp → tz-aware Chicago datetime.

    JSON API returns ISO-8601 ('2026-05-30T22:12:45').
    XML / legacy format is 'YYYYMMDD HH:MM:SS'.
    Try both so the client is forward-compatible.
    """
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y%m%d %H:%M:%S"):
        try:
            naive = datetime.strptime(raw, fmt)
            return _TZ.localize(naive)
        except ValueError:
            continue
    logger.warning("Unrecognised CTA timestamp format: %r", raw)
    return None


def _flag(val: Any) -> bool:
    return str(val) == "1"


class CtaTrainClient:
    def __init__(self, api_key: str, timeout: int = 10):
        self._key = api_key
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CtaTrainClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Arrivals
    # ------------------------------------------------------------------

    def get_arrivals(self, mapid: int, max_results: int = 10) -> list[dict]:
        """
        Fetch arrival predictions for a parent station.

        Returns a list of normalized dicts — one per ETA record.
        """
        params = {
            "key": self._key,
            "mapid": mapid,
            "max": max_results,
            "outputType": "JSON",
        }
        try:
            resp = self._client.get(_ARRIVALS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("arrivals fetch failed mapid=%s: %s", mapid, exc)
            return []

        ctatt = data.get("ctatt", {})
        err_code = ctatt.get("errCd", "0")
        if str(err_code) != "0":
            logger.error("CTA arrivals API error mapid=%s: %s", mapid, ctatt.get("errNm"))
            return []

        etas = ctatt.get("eta", []) or []
        if isinstance(etas, dict):
            etas = [etas]

        results = []
        for eta in etas:
            results.append(
                {
                    "station_id": eta.get("staId"),
                    "stop_id": eta.get("stpId"),
                    "station_name": eta.get("staNm"),
                    "stop_desc": eta.get("stpDe"),
                    "run_number": eta.get("rn"),
                    "route": eta.get("rt"),
                    "destination_stop_id": eta.get("destSt"),
                    "destination": eta.get("destNm"),
                    "direction": eta.get("trDr"),
                    "prdt": _parse_cta_dt(eta.get("prdt")),
                    "arr_t": _parse_cta_dt(eta.get("arrT")),
                    "is_approaching": _flag(eta.get("isApp")),
                    "is_scheduled": _flag(eta.get("isSch")),
                    "is_delayed": _flag(eta.get("isDly")),
                    "is_faulty": _flag(eta.get("isFlt")),
                    "lat": eta.get("lat"),
                    "lon": eta.get("lon"),
                    "heading": eta.get("heading"),
                    "raw": json.dumps(eta),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self, route: str) -> list[dict]:
        """
        Fetch all current train positions for a route.

        Returns a list of normalized dicts — one per train.
        """
        api_rt = _ROUTE_IDS.get(route.lower())
        if not api_rt:
            logger.error("Unknown route: %s", route)
            return []

        params = {"key": self._key, "rt": api_rt, "outputType": "JSON"}
        try:
            resp = self._client.get(_POSITIONS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("positions fetch failed route=%s: %s", route, exc)
            return []

        ctatt = data.get("ctatt", {})
        if str(ctatt.get("errCd", "0")) != "0":
            logger.error("CTA positions API error route=%s: %s", route, ctatt.get("errNm"))
            return []

        route_list = ctatt.get("route", []) or []
        if isinstance(route_list, dict):
            route_list = [route_list]

        trains = []
        for r in route_list:
            train_list = r.get("train", []) or []
            if isinstance(train_list, dict):
                train_list = [train_list]
            for t in train_list:
                trains.append(
                    {
                        "run_number": t.get("rn"),
                        "route": api_rt,
                        "destination": t.get("destNm"),
                        "direction": t.get("trDr"),
                        "next_station_id": t.get("nextStaId"),
                        "next_station_name": t.get("nextStaNm"),
                        "prdt": _parse_cta_dt(t.get("prdt")),
                        "arr_t": _parse_cta_dt(t.get("arrT")),
                        "is_approaching": _flag(t.get("isApp")),
                        "is_delayed": _flag(t.get("isDly")),
                        "lat": t.get("lat"),
                        "lon": t.get("lon"),
                        "heading": t.get("heading"),
                    }
                )
        return trains
