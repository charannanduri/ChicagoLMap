"""
CTA Train Tracker API client — JSON edition.

All CTA calls use outputType=JSON so we avoid XML parsing entirely.
Public surface:
    get_train_positions(api_key, route)                -> list[dict]
    get_train_positions_via_arrivals(api_key, route, station_map) -> list[dict]
    get_arrivals(api_key, mapid, route=None, max=8)    -> list[dict]
    get_station_arrivals(api_key, mapid, route, max)   -> list[dict]  (compat shim)
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytz
import requests

_CHICAGO = pytz.timezone("America/Chicago")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

_POSITIONS_URL = "http://lapi.transitchicago.com/api/1.0/ttpositions.aspx"
_ARRIVALS_URL  = "http://lapi.transitchicago.com/api/1.0/ttarrivals.aspx"
_FOLLOW_URL    = "http://lapi.transitchicago.com/api/1.0/ttfollow.aspx"

# User-facing route key → CTA API rt value
_API_RT: dict[str, str] = {
    "red": "Red", "blue": "Blue",
    "brn": "Brn", "brown": "Brn",
    "g": "G", "green": "G",
    "o": "Org", "org": "Org", "orange": "Org",
    "p": "P", "purple": "P",
    "pnk": "Pink", "pink": "Pink",
    "y": "Y", "yellow": "Y",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _to_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _to_float(v) -> float | None:
    try:
        return float(v) if v is not None and str(v).strip() else None
    except (ValueError, TypeError):
        return None


def _eta_minutes(arr_t_str: str | None) -> int | None:
    """Convert CTA arrival time string to minutes from now.

    CTA timestamps are Chicago local time (naive, no tz suffix).
    We attach America/Chicago so the subtraction is correct on any server
    timezone — Render runs UTC which would make all ETAs appear negative
    without this localisation.
    """
    if not arr_t_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y%m%d %H:%M:%S"):
        try:
            naive = datetime.strptime(arr_t_str, fmt)
            arr_dt = _CHICAGO.localize(naive)
            now    = datetime.now(_CHICAGO)
            return max(0, int((arr_dt - now).total_seconds() // 60))
        except ValueError:
            continue
    return None


def _as_list(v) -> list:
    """CTA JSON wraps single-element arrays as plain objects; normalise."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _ctatt_ok(ctatt: dict, label: str) -> bool:
    err = ctatt.get("errCd", "0")
    if str(err) != "0":
        logging.error(f"CTA API error ({label}): {ctatt.get('errNm')}")
        return False
    return True


# ── public API ───────────────────────────────────────────────────────────────

def get_train_positions(api_key: str, route: str) -> list[dict]:
    """
    Live GPS positions for a route via ttpositions (JSON).
    Returns [] when no GPS data is available — caller should fall back to
    get_train_positions_via_arrivals().
    Each returned dict includes position_source='gps'.
    """
    api_rt = _API_RT.get(route.lower())
    if not api_rt:
        logging.error(f"Unknown route: '{route}'")
        return []

    try:
        resp = requests.get(
            _POSITIONS_URL,
            params={"key": api_key, "rt": api_rt, "outputType": "JSON"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logging.error(f"Positions request failed for '{route}': {exc}")
        return []

    ctatt = data.get("ctatt", {})
    if not _ctatt_ok(ctatt, f"positions/{route}"):
        return []

    # Find the matching route node (case-insensitive on @name)
    route_node = None
    for r in _as_list(ctatt.get("route")):
        if (r.get("@name") or "").lower() == api_rt.lower():
            route_node = r
            break

    if route_node is None:
        logging.info(f"No route node for '{route}' in positions response.")
        return []

    trains_raw = _as_list(route_node.get("train"))
    if not trains_raw:
        logging.info(f"No GPS trains on '{route}'.")
        return []

    trains: list[dict] = []
    for t in trains_raw:
        lat = _to_float(t.get("lat"))
        lon = _to_float(t.get("lon"))
        if lat is None or lon is None:
            continue
        trains.append({
            "lat":             lat,
            "lon":             lon,
            "heading":         _to_int(t.get("heading")) or 0,
            "run_number":      t.get("rn"),
            "next_sta_id":     _to_int(t.get("nextStaId")),
            "next_sta_name":   t.get("nextStaNm"),
            "is_approaching":  t.get("isApp") == "1",
            "is_delayed":      t.get("isDly") == "1",
            "dest_sta_id":     _to_int(t.get("destSt")),
            "dest_name":       t.get("destNm"),
            "direction_code":  _to_int(t.get("trDr")),
            "arrival_time":    t.get("arrT"),
            "position_source": "gps",
        })

    logging.info(f"GPS positions: {len(trains)} trains for '{route}'.")
    return trains


def get_arrivals(
    api_key: str,
    mapid: int,
    route: str | None = None,
    max_results: int = 8,
) -> list[dict]:
    """
    Fetch next arrivals at a parent station (mapid) via ttarrivals (JSON).
    Optionally filter by route.  Returns raw arrival dicts.
    """
    params: dict = {"key": api_key, "mapid": mapid, "max": max_results, "outputType": "JSON"}
    if route:
        api_rt = _API_RT.get(route.lower())
        if api_rt:
            params["rt"] = api_rt

    try:
        resp = requests.get(_ARRIVALS_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logging.error(f"Arrivals request failed for mapid={mapid}: {exc}")
        return []

    ctatt = data.get("ctatt", {})
    if not _ctatt_ok(ctatt, f"arrivals/{mapid}"):
        return []

    results: list[dict] = []
    for eta in _as_list(ctatt.get("eta")):
        arr_t = eta.get("arrT")
        results.append({
            "route":          eta.get("rt"),
            "run_number":     eta.get("rn"),
            "station_name":   eta.get("staNm"),
            "stop_desc":      eta.get("stpDe"),   # "Service toward X"
            "dest_name":      eta.get("destNm"),
            "direction_code": _to_int(eta.get("trDr")),
            "eta_minutes":    _eta_minutes(arr_t),
            "arrival_time":   arr_t,
            "is_approaching": eta.get("isApp") == "1",
            "is_scheduled":   eta.get("isSch") == "1",
            "is_delayed":     eta.get("isDly") == "1",
            # GPS coords are usually null in arrivals; included for completeness
            "lat":            _to_float(eta.get("lat")),
            "lon":            _to_float(eta.get("lon")),
            "heading":        _to_int(eta.get("heading")),
        })

    return results


def get_train_positions_via_arrivals(
    api_key: str,
    route: str,
    station_map: dict[int, dict],
) -> list[dict]:
    """
    Fallback when GPS data is unavailable (ttpositions returns empty).
    Queries ttarrivals for every station in station_map in parallel and plots
    each unique run at its next station's coordinates.

    station_map: {mapid: {'name': str, 'lat': float, 'lon': float}}
    """
    api_rt = _API_RT.get(route.lower())
    if not api_rt or not station_map:
        return []

    def fetch_one(args: tuple) -> list[dict]:
        mapid, info = args
        raw = get_arrivals(api_key, mapid, route=route, max_results=20)
        results = []
        for a in raw:
            if (a.get("route") or "").upper() != api_rt.upper():
                continue
            rn = a.get("run_number")
            if not rn:
                continue
            results.append({
                "run_number":      rn,
                "lat":             info["lat"],
                "lon":             info["lon"],
                "heading":         0,
                "next_sta_name":   info["name"],
                "is_approaching":  a["is_approaching"],
                "is_delayed":      a["is_delayed"],
                "dest_name":       a["dest_name"],
                "direction_code":  a["direction_code"],
                "arrival_time":    a["arrival_time"],
                "eta_minutes":     a["eta_minutes"],   # used for closest-station selection
                "position_source": "schedule",
            })
        return results

    # For each run number, keep the station it is CLOSEST to (smallest eta_minutes).
    # This gives the best proxy position on the map — e.g. a train predicted to
    # arrive at Roosevelt in 1 min should appear near Roosevelt, not Cermak.
    seen: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for batch in pool.map(fetch_one, station_map.items()):
            for train in batch:
                rn = train["run_number"]
                new_eta = train.get("eta_minutes") or 999
                old_eta = (seen[rn].get("eta_minutes") or 999) if rn in seen else 999
                if rn not in seen or new_eta < old_eta:
                    seen[rn] = train

    logging.info(f"Arrivals fallback: {len(seen)} unique trains for '{route}'.")
    return list(seen.values())


def follow_run(api_key: str, run_number: str) -> dict:
    """
    Follow a single train by run number via ttfollow (JSON).

    Returns the train's current position plus every UPCOMING stop to the end of
    its run, in travel order. Works underground because CTA's tracker predicts
    arrivals from schedule + signal data even where GPS is unavailable.

    Shape:
        {
          "run_number": str,
          "route": str | None,          # CTA rt, e.g. "Red"
          "destination": str | None,
          "position": {"lat","lon","heading"} | None,
          "stops": [ {station_id, station_name, stop_desc, dest_name,
                      direction_code, eta_minutes, arrival_time,
                      is_approaching, is_scheduled, is_delayed}, ... ]
        }
    Returns {} on any error.
    """
    params = {"key": api_key, "runnumber": run_number, "outputType": "JSON"}
    try:
        resp = requests.get(_FOLLOW_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logging.error(f"Follow request failed for run={run_number}: {exc}")
        return {}

    ctatt = data.get("ctatt", {})
    if not _ctatt_ok(ctatt, f"follow/{run_number}"):
        return {}

    pos = ctatt.get("position") or {}
    route = None
    destination = None
    stops: list[dict] = []
    for eta in _as_list(ctatt.get("eta")):
        route = route or eta.get("rt")
        destination = destination or eta.get("destNm")
        arr_t = eta.get("arrT")
        stops.append({
            "station_id":     _to_int(eta.get("staId")),
            "station_name":   eta.get("staNm"),
            "stop_desc":      eta.get("stpDe"),
            "dest_name":      eta.get("destNm"),
            "direction_code": _to_int(eta.get("trDr")),
            "eta_minutes":    _eta_minutes(arr_t),
            "arrival_time":   arr_t,
            "is_approaching": eta.get("isApp") == "1",
            "is_scheduled":   eta.get("isSch") == "1",
            "is_delayed":     eta.get("isDly") == "1",
        })

    position = None
    if pos:
        position = {
            "lat":     _to_float(pos.get("lat")),
            "lon":     _to_float(pos.get("lon")),
            "heading": _to_int(pos.get("heading")),
        }

    return {
        "run_number":  run_number,
        "route":       route,
        "destination": destination,
        "position":    position,
        "stops":       stops,
    }


# Backward-compat shim used by the hardware /api/station/<mapid>/next endpoint
def get_station_arrivals(
    api_key: str,
    mapid: int,
    route: str | None = None,
    max_results: int = 4,
) -> list[dict]:
    """Thin wrapper around get_arrivals(); kept for the hardware API."""
    raw = get_arrivals(api_key, mapid, route=route, max_results=max_results)
    # Re-shape into the old format expected by api_station_next
    results = []
    now = datetime.now()
    for a in raw:
        results.append({
            "route":          a["route"],
            "station_name":   a["station_name"],
            "dest_name":      a["dest_name"],
            "direction_code": a["direction_code"],
            "eta_minutes":    a["eta_minutes"],
            "is_approaching": a["is_approaching"],
            "arrival_time":   a["arrival_time"],
        })
    return results
