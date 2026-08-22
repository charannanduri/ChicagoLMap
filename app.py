from __future__ import annotations

import os
import logging
import json
import zipfile
from io import BytesIO
from datetime import datetime, timedelta, timezone

import requests as _requests
from flask import Flask, jsonify, abort, send_from_directory, request
from cta_data import (
    get_train_positions,
    get_station_arrivals,
    get_train_positions_via_arrivals,
    get_arrivals,
    follow_run,
)
from fastkml import kml
from fastkml.features import Placemark
from shapely.geometry import mapping
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

app = Flask(__name__)

# --- Configuration ---
# It's best practice to load sensitive info like API keys from environment variables
# or a configuration file, not hardcode them directly in the source.
CTA_API_KEY = os.environ.get("CTA_API_KEY", "")

# Try to read API key from file if environment variable is not set
if not CTA_API_KEY and os.path.exists('api_key.txt'):
    try:
        with open('api_key.txt', 'r') as f:
            CTA_API_KEY = f.read().strip()
        logging.info("Successfully loaded API key from api_key.txt")
    except Exception as e:
        logging.error(f"Error reading API key from file: {e}")

if not CTA_API_KEY:
    logging.warning("CTA API Key not configured — train API calls will fail.")

# Delay predictor service URL (set DELAY_PREDICTOR_URL env var when predictor is running).
# When configured, station arrival popups will include ML-based delay forecasts.
DELAY_PREDICTOR_URL = os.environ.get("DELAY_PREDICTOR_URL", "").rstrip("/")

# Run the model in this process rather than calling the predictor service.
#
# Render's free allowance is 750 instance-hours per month across the account,
# and two services that are up together spend two of those per hour of wall
# clock -- which is what suspended both of them. /api/trains prices every train
# on every 15-second poll, so that one call guaranteed the second service was
# awake whenever anyone had the map open. Doing it here removes that.
#
# Set LOCAL_PREDICTOR=off to fall back to the HTTP service without a code
# change, if the in-process model ever misbehaves on a live instance.
_LOCAL_PREDICTOR_ENABLED = os.environ.get("LOCAL_PREDICTOR", "on").lower() != "off"
_local_predictor = None
if _LOCAL_PREDICTOR_ENABLED:
    try:
        import predictor_local as _local_predictor
    except Exception as exc:  # noqa: BLE001 — must never take the map down
        logging.warning("In-process predictor import failed: %s", exc)
        _local_predictor = None


# There was a keep-warm thread here that pinged the predictor's /health every
# ten minutes so Render's free tier would not spin it down between requests.
# It has been removed for two reasons.
#
# It was redundant. /api/trains prices every train through the predictor, and
# the map polls that every 15 seconds, so any open browser already keeps the
# predictor awake far more effectively than a ten-minute ping.
#
# It was also expensive in the one currency that turned out to matter. Render's
# free allowance is 750 instance-hours per month across the whole account, and
# two services running concurrently spend two hours of it per hour of wall
# clock. Pinning the predictor awake whenever this app was awake guaranteed
# both were up together, and the account was suspended part-way through the
# month. Cold starts are the cheaper problem, and slimming the predictor's
# dependencies (see cta-delay-predictor/requirements.txt) shortens those.

# CTA Customer Alerts API (keyless). Cached briefly so we don't hammer it.
_ALERTS_URL = "https://www.transitchicago.com/api/1.0/alerts.aspx"
_alerts_cache: dict = {"at": None, "data": []}
_ALERTS_TTL_SECONDS = 90

# Deployment environment — injected by Render, empty on localhost.
SITE_ENV = os.environ.get("SITE_ENV", "")        # "production" | ""

ALLOWED_ROUTES = {"red", "blue", "g", "brn", "p", "y", "pnk", "o"}

# Cache station maps so we only parse the KMZ once per route
_station_map_cache: dict[str, dict[int, dict]] = {}

# Maps normalised route key → CTA line name(s) that appear in KMZ "Rail Line" cells
_ROUTE_LINE_NAMES = {
    'red':  {'red'},
    'blue': {'blue'},
    'g':    {'green'},
    'brn':  {'brown'},
    'o':    {'orange'},
    'p':    {'purple', 'evanston express'},
    'pnk':  {'pink'},
    'y':    {'yellow'},
}


def _build_station_map(route: str) -> dict[int, dict]:
    """
    Parse CTA_RailStations.kmz and return {mapid: {name, lat, lon}} for every
    station on the given route.  mapid = 40000 + KMZ Station ID.
    Results are cached so the KMZ is only parsed once per route per process.
    """
    if route in _station_map_cache:
        return _station_map_cache[route]

    kmz_filename = 'CTA_RailStations.kmz'
    if not os.path.exists(kmz_filename):
        logging.error("CTA_RailStations.kmz not found; arrivals fallback unavailable.")
        return {}

    try:
        with zipfile.ZipFile(kmz_filename, 'r') as kmz:
            kml_files = [n for n in kmz.namelist() if n.lower().endswith('.kml')]
            if not kml_files:
                return {}
            kml_content = kmz.read(kml_files[0])
    except Exception as e:
        logging.error(f"Could not read KMZ for station map: {e}")
        return {}

    target_names = _ROUTE_LINE_NAMES.get(route, set())
    station_map: dict[int, dict] = {}

    try:
        from fastkml import kml as fastkml_mod
        from fastkml.features import Placemark as FKPlacemark

        k = fastkml_mod.KML.parse(BytesIO(kml_content))

        def _walk(node):
            yield node
            for child in (node.features if hasattr(node, 'features') else []) or []:
                yield from _walk(child)

        for pm in _walk(k):
            if not isinstance(pm, FKPlacemark) or not pm.description or not pm.geometry:
                continue

            soup = BeautifulSoup(pm.description, 'html.parser')

            rail_td = soup.find('td', string='Rail Line')
            if not rail_td:
                continue
            line_text = rail_td.find_next_sibling('td').get_text(strip=True)
            lines_in_kml = {
                seg.replace('Line', '').strip().lower()
                for seg in line_text.split(',')
            }
            if not target_names.intersection(lines_in_kml):
                continue

            sta_id_td = soup.find('td', string='Station ID')
            if not sta_id_td:
                continue
            try:
                sta_id = int(sta_id_td.find_next_sibling('td').get_text(strip=True))
            except (ValueError, TypeError):
                continue

            mapid = 40000 + sta_id
            station_map[mapid] = {
                'name': pm.name or 'Unknown',
                'lat':  pm.geometry.y,
                'lon':  pm.geometry.x,
            }
    except Exception as e:
        logging.error(f"Error building station map for route '{route}': {e}")

    logging.info(f"Station map for '{route}': {len(station_map)} stations cached.")
    _station_map_cache[route] = station_map
    return station_map

# --- Helper Function for GeoJSON --- (Added)
def load_and_filter_geojson(filename: str, route_filter_property: str, route_value: str):
    """Loads a GeoJSON file and filters features based on a property."""
    filepath = os.path.join('static_data', filename)
    try:
        with open(filepath, 'r') as f:
            geojson_data = json.load(f)

        if not isinstance(geojson_data, dict) or "features" not in geojson_data:
            logging.error(f"Invalid GeoJSON structure in {filename}")
            return None

        filtered_features = [
            feature for feature in geojson_data["features"]
            if feature.get("properties", {}).get(route_filter_property) == route_value
            # Handle cases where a stop might be on multiple routes (e.g., property is a list or comma-separated string)
            # This example assumes a simple string match. Adjust if needed based on actual GeoJSON structure.
        ]

        # Return a new GeoJSON FeatureCollection with only the filtered features
        return {
            "type": "FeatureCollection",
            "features": filtered_features
        }

    except FileNotFoundError:
        logging.error(f"GeoJSON file not found: {filepath}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {filepath}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred loading/filtering {filepath}: {e}")
        return None

# --- Helper Function for KML Stops to GeoJSON --- (MODIFIED)
def load_and_filter_kml_stops(kml_content: bytes, route_value: str):
    """Loads KML content, filters Placemarks by route using description HTML, returns GeoJSON FeatureCollection."""
    features = []
    try:
        # fastkml >= 1.0: parse from a file-like object; `from_string` silently yields no features.
        k = kml.KML.parse(BytesIO(kml_content))

        # Recursively walk the KML tree to collect every Placemark, regardless of nesting depth.
        def walk(node):
            yield node
            for child in (node.features if hasattr(node, 'features') else []) or []:
                yield from walk(child)

        all_placemarks = [f for f in walk(k) if isinstance(f, Placemark)]
        logging.info(f"Found {len(all_placemarks)} total placemarks after parsing KML structure.")

        # Use BeautifulSoup to parse description and filter
        for pm in all_placemarks:
            route_match = False
            station_name = pm.name or "Unknown Station"

            if pm.description:
                try:
                    soup = BeautifulSoup(pm.description, 'html.parser')
                    
                    # Extract address
                    address_td = soup.find('td', string="Address")
                    address = ""
                    if address_td and address_td.find_next_sibling('td'):
                        address = address_td.find_next_sibling('td').get_text(strip=True)
                        logging.debug(f"Placemark '{station_name}': Found address: '{address}'")
                    
                    # Extract rail line (existing code)
                    rail_line_label_td = soup.find('td', string="Rail Line")
                    if rail_line_label_td and rail_line_label_td.find_next_sibling('td'):
                        rail_line_value_td = rail_line_label_td.find_next_sibling('td')
                        line_text = rail_line_value_td.get_text(strip=True)

                        logging.debug(f"Placemark '{station_name}': Found raw line text: '{line_text}'")
                        # Split by comma and clean each line
                        lines_in_kml = []
                        for line in line_text.split(','):
                            # Remove "Line" and clean up
                            cleaned = line.replace("Line", "").strip().lower()
                            # Handle special cases like "Green Line" -> "g"
                            if cleaned == "green":
                                cleaned = "g"
                            elif cleaned == "brown":
                                cleaned = "brn"
                            elif cleaned == "purple":
                                cleaned = "p"
                            elif cleaned == "yellow":
                                cleaned = "y"
                            elif cleaned == "pink":
                                cleaned = "pnk"
                            elif cleaned == "orange":
                                cleaned = "o"
                            lines_in_kml.append(cleaned)
                        
                        logging.debug(f"Placemark '{station_name}': Normalized lines: {lines_in_kml}, Checking for: '{route_value.lower()}'")

                        if route_value.lower() in lines_in_kml:
                            logging.debug(f"Placemark '{station_name}': Matched route '{route_value.lower()}'")
                            route_match = True

                except Exception as parse_e:
                    logging.warning(f"Error parsing description HTML for placemark '{station_name}': {parse_e}")

            if route_match:
                try:
                    geojson_geometry = mapping(pm.geometry)
                    # Extract Station ID so the frontend can call /api/station/<mapid>/arrivals
                    sta_id_td = soup.find('td', string='Station ID')
                    sta_id = None
                    mapid = None
                    if sta_id_td and sta_id_td.find_next_sibling('td'):
                        try:
                            sta_id = int(sta_id_td.find_next_sibling('td').get_text(strip=True))
                            mapid = 40000 + sta_id
                        except (ValueError, TypeError):
                            pass
                    feature = {
                        "type": "Feature",
                        "geometry": geojson_geometry,
                        "properties": {
                            "name": station_name,
                            "address": address,
                            "route": route_value,
                            "mapid": mapid,
                        }
                    }
                    features.append(feature)
                except Exception as geo_e:
                    logging.warning(f"Could not convert geometry for placemark '{station_name}': {geo_e}")

    except Exception as e:
        logging.error(f"Error processing KML content: {e}", exc_info=True)
        return None

    if not features:
        logging.warning(f"No matching stops found for route '{route_value}' after parsing KML descriptions.")

    return {
        "type": "FeatureCollection",
        "features": features
    }

# --- API Routes ---
@app.route('/api/trains/<route>', methods=['GET'])
def api_get_trains(route):
    """API endpoint to get train positions for a specific route."""
    route_lower = route.lower()
    logging.info(f"Received request for route: {route_lower}")

    if route_lower not in ALLOWED_ROUTES:
        logging.warning(f"Request received for invalid route: {route_lower}")
        abort(404, description=f"Invalid route specified. Allowed routes: {list(ALLOWED_ROUTES)}")

    if not CTA_API_KEY:
        logging.error("Cannot fetch train data: CTA API Key is not configured.")
        abort(500, description="Server configuration error: API key missing.") # 500 Internal Server Error

    train_data = get_train_positions(CTA_API_KEY, route_lower)
    position_source = "gps"

    if not train_data:
        logging.info(f"GPS empty for '{route_lower}'; using arrivals fallback.")
        station_map = _build_station_map(route_lower)
        if station_map:
            train_data = get_train_positions_via_arrivals(CTA_API_KEY, route_lower, station_map)
            position_source = "schedule"

    _attach_predicted_eta(train_data)

    return jsonify({
        "route":           route_lower,
        "trains":          train_data,
        "position_source": position_source,
        "train_count":     len(train_data),
    })

# --- GeoJSON API Routes --- (Updated)
@app.route('/api/geojson/routes/<route>', methods=['GET'])
def api_get_geojson_route(route):
    """Serves GeoJSON LineString for the given route from the pre-built GTFS shapes file."""
    route_lower = route.lower()
    filepath = os.path.join('static_data', 'cta_rail_lines.geojson')
    if not os.path.exists(filepath):
        return jsonify({"type": "FeatureCollection", "features": []})
    try:
        with open(filepath) as f:
            all_lines = json.load(f)
        if route_lower == 'all':
            return jsonify(all_lines)
        features = [
            feat for feat in all_lines.get('features', [])
            if feat.get('properties', {}).get('route') == route_lower
        ]
        return jsonify({"type": "FeatureCollection", "features": features})
    except Exception as e:
        logging.error(f"Error serving route GeoJSON for '{route}': {e}")
        return jsonify({"type": "FeatureCollection", "features": []})

@app.route('/api/geojson/stops/<route>', methods=['GET'])
def api_get_geojson_stops(route):
    """Serves GeoJSON points for stops on a specific route, extracted from KMZ."""
    route_lower = route.lower()
    kmz_filename = 'CTA_RailStations.kmz'
    kml_doc_name = 'doc.kml' # Common default name within KMZ

    if not os.path.exists(kmz_filename):
        logging.error(f"KMZ file not found: {kmz_filename}")
        abort(500, description=f"Server configuration error: {kmz_filename} not found.")

    try:
        with zipfile.ZipFile(kmz_filename, 'r') as kmz:
            # Find the KML file within the archive (might not always be doc.kml)
            kml_files = [name for name in kmz.namelist() if name.lower().endswith('.kml')]
            if not kml_files:
                logging.error(f"No .kml file found inside {kmz_filename}")
                abort(500, description="Invalid KMZ structure: No KML file found.")
            # Assuming the first KML file found is the main one
            kml_doc_name = kml_files[0]
            logging.info(f"Extracting KML file: {kml_doc_name} from {kmz_filename}")
            kml_content = kmz.read(kml_doc_name)

    except zipfile.BadZipFile:
        logging.error(f"Error: {kmz_filename} is not a valid zip file or is corrupted.")
        abort(500, description="Server error: Invalid KMZ file.")
    except KeyError:
        logging.error(f"Error: Default KML entry '{kml_doc_name}' not found in {kmz_filename}. Found: {kmz.namelist()}")
        abort(500, description="Server error: Could not find KML data in KMZ.")
    except Exception as e:
         logging.error(f"Error reading KMZ file {kmz_filename}: {e}")
         abort(500, description="Server error reading KMZ file.")

    # Process the extracted KML content
    geojson_result = load_and_filter_kml_stops(kml_content, route_lower)

    if geojson_result is None:
        # Error occurred during parsing or filtering, already logged
        abort(500, description=f"Error processing KML data for stops on route '{route_lower}'. Check server logs.")

    return jsonify(geojson_result)

# ── Station arrivals endpoint (used by map popups) ────────────────────────────

def _delay_status_label(delay_minutes: float | None, is_scheduled: bool) -> str:
    """Human-readable delay status for display."""
    if delay_minutes is None:
        return "Scheduled" if is_scheduled else "On Time"
    if delay_minutes > 1:
        return f"{int(round(delay_minutes))} min late"
    if delay_minutes < -1:
        return f"{int(round(abs(delay_minutes)))} min early"
    return "On Time"


def _try_predictor(mapid: int) -> dict[str, dict]:
    """
    Call the delay predictor service if configured.
    Returns {run_number: {delay_minutes, delay_status, p10, p90}} or {}.
    Silently returns {} if the service is down or not configured.
    """
    if not DELAY_PREDICTOR_URL:
        return {}
    try:
        # Generous read timeout: the predictor free-tier instance queries the
        # CTA API and the database per request, which routinely exceeds 2 s.
        resp = _requests.get(
            f"{DELAY_PREDICTOR_URL}/stations/{mapid}/arrivals",
            params={"n": 20},
            timeout=(3.05, 8),
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logging.warning("Delay predictor unavailable for station %s: %s", mapid, exc)
        return {}

    result: dict[str, dict] = {}
    for item in payload.get("arrivals", []):
        rn = str(item.get("run_number") or "")
        if not rn:
            continue
        result[rn] = {
            "delay_minutes":  item.get("model_delay_minutes"),
            "delay_status":   item.get("delay_status"),
            "p10_minutes":    item.get("p10_minutes"),
            "p90_minutes":    item.get("p90_minutes"),
        }
    return result


def _shift_iso(arr_t: str | None, delay_min) -> str | None:
    """Add delay_min minutes to a CTA local ISO timestamp; None if unparseable."""
    if not arr_t or delay_min is None:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y%m%d %H:%M:%S"):
        try:
            dt = datetime.strptime(arr_t, fmt)
            return (dt + timedelta(minutes=float(delay_min))).strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            continue
    return None


_ROUTE_TO_ARRIVALS_KEY = {
    "red": "Red", "blue": "Blue", "g": "G", "brn": "Brn",
    "o": "Org", "p": "P", "pnk": "Pink", "y": "Y",
}


def _attach_predicted_eta(trains: list[dict]) -> None:
    """
    Add our ML-predicted arrival to each live train, in place.

    The map animates trains toward their next stop using `predicted_eta_seconds`
    when we have a prediction, so the motion reflects when we think the train
    will *actually* arrive rather than the CTA's raw estimate. Every train is
    priced in a single batch call — one request per poll, not one per train.

    Degrades silently: without a prediction the map falls back to `eta_seconds`.
    """
    if not trains:
        return
    if _local_predictor is None and not DELAY_PREDICTOR_URL:
        return

    payload = {"trains": [
        {
            "run_number": str(t.get("run_number") or ""),
            "route": _ROUTE_TO_ARRIVALS_KEY.get((t.get("route") or "").lower(), t.get("route")),
            "station_id": str(t.get("next_sta_id") or ""),
            "direction": str(t.get("direction_code") or ""),
            "eta_seconds": t.get("eta_seconds"),
            "is_delayed": bool(t.get("is_delayed")),
            "is_scheduled": bool(t.get("is_scheduled")),
        }
        for t in trains
    ]}

    # In-process first; the HTTP service is the fallback, not the default.
    if _local_predictor is not None and _local_predictor.is_ready():
        try:
            by_run = _local_predictor.predict_batch(payload["trains"])
        except Exception as exc:  # noqa: BLE001
            logging.warning("In-process batch prediction failed: %s", exc)
            by_run = {}
    else:
        if not DELAY_PREDICTOR_URL:
            return
        try:
            resp = _requests.post(
                f"{DELAY_PREDICTOR_URL}/predict/batch", json=payload, timeout=(3.05, 8)
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:
            logging.warning("Batch prediction failed: %s", exc)
            return
        by_run = {str(r.get("run_number") or ""): r for r in results}
    for t in trains:
        pred = by_run.get(str(t.get("run_number") or ""))
        if not pred:
            continue
        delay = pred.get("delay_minutes")
        t["model_delay_minutes"] = delay
        t["delay_status"] = pred.get("delay_status")
        eta = t.get("eta_seconds")
        if delay is not None and eta is not None:
            # Never let a prediction pull an arrival into the past.
            t["predicted_eta_seconds"] = max(0, int(round(eta + delay * 60)))


def _predictor_run(run_number: str) -> dict[int, dict]:
    """
    Ask the predictor service for per-stop ML delays for a run.
    Returns {station_id: {delay_minutes, delay_status}} or {} when the
    predictor is unconfigured or unavailable (graceful degradation).
    """
    if not DELAY_PREDICTOR_URL:
        return {}
    try:
        resp = _requests.get(
            f"{DELAY_PREDICTOR_URL}/runs/{run_number}",
            timeout=(3.05, 8),
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logging.warning("Predictor run lookup failed for %s: %s", run_number, exc)
        return {}

    out: dict[int, dict] = {}
    for stop in payload.get("stops", []):
        sid = stop.get("station_id")
        try:
            sid_int = int(sid)
        except (ValueError, TypeError):
            continue
        out[sid_int] = {
            "delay_minutes": stop.get("model_delay_minutes"),
            "delay_status":  stop.get("delay_status"),
        }
    return out


@app.route('/api/run/<run_number>/follow', methods=['GET'])
def api_run_follow(run_number):
    """
    Follow a train by run number: its upcoming stops with CTA ETAs enriched
    with ML delay predictions and predicted clock times. Used by the iOS app's
    trip-tracking view. Underground-tolerant (CTA tracker predicts without GPS).
    """
    if not CTA_API_KEY:
        abort(500, description="CTA API key not configured.")

    data = follow_run(CTA_API_KEY, run_number)
    if not data:
        return jsonify({
            "run_number": run_number, "route": None, "destination": None,
            "position": None, "stops": [],
        })

    predictions = _predictor_run(run_number)
    for stop in data["stops"]:
        sid = stop.get("station_id")
        pred = predictions.get(sid, {}) if sid is not None else {}
        delay = pred.get("delay_minutes")
        stop["delay_minutes"] = delay
        stop["delay_status"] = pred.get("delay_status")
        stop["predictor_active"] = bool(pred)
        stop["predicted_arrival_time"] = _shift_iso(stop.get("arrival_time"), delay)

    return jsonify(data)


_ROUTE_NAME_TO_KEY = {
    "red": "red", "blue": "blue", "brown": "brn", "brn": "brn",
    "green": "g", "g": "g", "orange": "o", "org": "o",
    "purple": "p", "purple express": "p", "p": "p",
    "pink": "pnk", "pnk": "pnk", "yellow": "y", "y": "y",
}


def _fetch_alerts() -> list[dict]:
    """Fetch active CTA train alerts, simplified. Cached for _ALERTS_TTL_SECONDS."""
    now = datetime.now(timezone.utc)
    cached_at = _alerts_cache["at"]
    if cached_at and (now - cached_at).total_seconds() < _ALERTS_TTL_SECONDS:
        return _alerts_cache["data"]

    try:
        resp = _requests.get(
            _ALERTS_URL,
            params={"outputType": "JSON", "activeonly": "true"},
            timeout=8,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logging.warning("CTA alerts fetch failed: %s", exc)
        # Serve stale cache if we have it, else empty.
        return _alerts_cache["data"] or []

    raw_alerts = payload.get("CTAAlerts", {}).get("Alert", [])
    if isinstance(raw_alerts, dict):
        raw_alerts = [raw_alerts]

    def _cdata(v):
        if isinstance(v, dict):
            return v.get("#cdata-section") or v.get("#text") or ""
        return v or ""

    simplified: list[dict] = []
    for a in raw_alerts:
        # Which train lines does this alert touch?
        services = (a.get("ImpactedService") or {}).get("Service") or []
        if isinstance(services, dict):
            services = [services]
        route_keys: list[str] = []
        for svc in services:
            if str(svc.get("ServiceType")) != "T":   # T = train
                continue
            name = (svc.get("ServiceName") or svc.get("ServiceId") or "").strip()
            key = _ROUTE_NAME_TO_KEY.get(name.lower())
            if key and key not in route_keys:
                route_keys.append(key)

        # Keep train alerts (route-scoped) and system-wide train notices.
        is_train = any(str(s.get("ServiceType")) == "T" for s in services) if services else False
        if not is_train and route_keys == []:
            continue

        simplified.append({
            "id": str(a.get("AlertId") or ""),
            "headline": _cdata(a.get("Headline")).strip(),
            "description": _cdata(a.get("ShortDescription")).strip(),
            "impact": (a.get("Impact") or "").strip(),
            "severity": _to_int(a.get("SeverityScore")) or 0,
            "routes": route_keys,
            "url": _cdata(a.get("AlertURL")).strip(),
        })

    # Most severe first.
    simplified.sort(key=lambda x: x["severity"], reverse=True)
    _alerts_cache["at"] = now
    _alerts_cache["data"] = simplified
    return simplified


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@app.route('/api/alerts', methods=['GET'])
def api_alerts():
    """Active CTA train service alerts (closures, delays, reroutes)."""
    route = (request.args.get("route") or "").lower() or None
    alerts = _fetch_alerts()
    if route:
        alerts = [a for a in alerts if not a["routes"] or route in a["routes"]]
    return jsonify({"alerts": alerts, "as_of": datetime.now(timezone.utc).isoformat()})


@app.route('/api/feedback', methods=['POST'])
def api_feedback():
    """
    Relay a rider's arrival-accuracy correction to the predictor service, which
    owns the database. Body: {run_number, station_id, route,
    predicted_delay_minutes, delta_minutes}.
    """
    if not DELAY_PREDICTOR_URL:
        abort(503, description="Feedback service not configured.")
    body = request.get_json(silent=True) or {}
    if "delta_minutes" not in body:
        abort(400, description="delta_minutes is required.")
    try:
        resp = _requests.post(
            f"{DELAY_PREDICTOR_URL}/feedback",
            json=body,
            timeout=(3.05, 8),
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except Exception as exc:
        logging.warning("Feedback relay failed: %s", exc)
        abort(502, description="Could not record feedback right now.")


@app.route('/api/station/<int:mapid>/arrivals', methods=['GET'])
def api_station_arrivals(mapid):
    """
    Next arrivals at a station, grouped by route+direction, enriched with
    ML delay predictions when the predictor service is running.

    Query params:
        route  — optional CTA route filter (e.g. "red")
        n      — max arrivals to fetch (default 10, max 20)
    """
    if not CTA_API_KEY:
        abort(500, description="CTA API key not configured.")

    route_filter = request.args.get("route", "").lower() or None
    n = min(int(request.args.get("n", 10)), 20)

    raw = get_arrivals(CTA_API_KEY, mapid, route=route_filter, max_results=n)

    if not raw:
        return jsonify({
            "mapid": mapid,
            "station_name": None,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "directions": [],
        })

    # Try to get ML predictions; gracefully absent when predictor isn't running
    predictions = _try_predictor(mapid)

    station_name = raw[0].get("station_name") if raw else None

    # Group arrivals by (route, direction_label) — direction_label from stop_desc
    from collections import defaultdict
    groups: dict[tuple, list[dict]] = defaultdict(list)

    for a in raw:
        rt = a.get("route") or ""
        # "Service toward Howard" → "toward Howard"
        desc = a.get("stop_desc") or ""
        direction_label = desc.replace("Service ", "").strip() or f"Direction {a.get('direction_code')}"
        key = (rt, direction_label)

        rn = str(a.get("run_number") or "")
        pred = predictions.get(rn, {})
        delay_min = pred.get("delay_minutes")
        is_sched = a.get("is_scheduled", False)

        # Prefer ML status label if available, else derive from CTA isDly flag
        if pred.get("delay_status"):
            status_str = {
                "behind":  f"{int(round(abs(delay_min or 0)))} min late",
                "ahead":   f"{int(round(abs(delay_min or 0)))} min early",
                "on_time": "On Time",
            }.get(pred["delay_status"], "On Time")
        else:
            status_str = _delay_status_label(
                delay_min if delay_min is not None else (2.0 if a.get("is_delayed") else None),
                is_sched,
            )

        groups[key].append({
            "run_number":       rn,
            "destination":      a.get("dest_name"),
            "eta_minutes":      a.get("eta_minutes"),
            "arrival_time":     a.get("arrival_time"),
            "is_approaching":   a.get("is_approaching"),
            "is_scheduled":     is_sched,
            "is_delayed":       a.get("is_delayed"),
            "delay_minutes":    delay_min,
            "delay_status":     status_str,
            "p10_minutes":      pred.get("p10_minutes"),
            "p90_minutes":      pred.get("p90_minutes"),
            "predictor_active": bool(pred),
        })

    directions = [
        {"route": rt, "direction_label": label, "trains": trains}
        for (rt, label), trains in groups.items()
    ]

    return jsonify({
        "mapid":        mapid,
        "station_name": station_name,
        "as_of":        datetime.now(timezone.utc).isoformat(),
        "directions":   directions,
    })


# --- Hardware-facing endpoints --- (compact JSON for the ESP32 companion device)
#
# These endpoints exist to feed the planned physical PCB with RGB LEDs per
# station and an e-paper next-arrival display. See docs/HARDWARE.md for the
# overall design. They're deliberately simple and poll-friendly so an ESP32
# can hit them on a ~10s cadence.

# For the PoC we only expose Red Line. Direction buckets are keyed by the
# destination terminal. Expand this table as more lines come online.
ROUTE_DIRECTION_BUCKETS = {
    'red': {
        'north': {'Howard'},
        'south': {'95th/Dan Ryan'},
    },
}

def _bucket_direction(route: str, dest_name: str | None) -> str | None:
    """Map a CTA destination name to a cardinal direction bucket for the given route."""
    if not dest_name:
        return None
    buckets = ROUTE_DIRECTION_BUCKETS.get(route, {})
    for direction, dest_set in buckets.items():
        if dest_name in dest_set:
            return direction
    return None


@app.route('/api/stations/<route>/status', methods=['GET'])
def api_station_status(route):
    """Per-station, per-direction occupancy for the LED board.

    A direction at a station is "lit" when there's at least one train on that
    route currently approaching or stopped at that station heading that way.
    """
    route_lower = route.lower()
    if route_lower not in ALLOWED_ROUTES:
        abort(404, description=f"Invalid route. Allowed: {sorted(ALLOWED_ROUTES)}")
    if route_lower not in ROUTE_DIRECTION_BUCKETS:
        abort(501, description=f"Station status not yet implemented for route '{route_lower}'. "
                                f"Supported: {sorted(ROUTE_DIRECTION_BUCKETS)}")
    if not CTA_API_KEY:
        abort(500, description="Server configuration error: API key missing.")

    trains = get_train_positions(CTA_API_KEY, route_lower)

    # Build {station_name: {direction: bool}}
    # Station names come from trains' `next_sta_name`; the LED board already knows
    # the full static station list from its own map, so we only need to report
    # stations with activity. That keeps the payload tiny.
    occupied: dict[str, dict[str, bool]] = {}
    for t in trains:
        station = t.get('next_sta_name')
        if not station:
            continue
        # Only count trains that are effectively at the station (approaching).
        # Trains further out will show up on subsequent polls as they get closer.
        if not t.get('is_approaching'):
            continue
        direction = _bucket_direction(route_lower, t.get('dest_name'))
        if direction is None:
            continue
        occupied.setdefault(station, {'north': False, 'south': False})
        occupied[station][direction] = True

    stations = [
        {'name': name, 'north': dirs['north'], 'south': dirs['south']}
        for name, dirs in sorted(occupied.items())
    ]

    return jsonify({
        'route': route_lower,
        'as_of': datetime.now(timezone.utc).isoformat(),
        'stations': stations,
    })


@app.route('/api/station/<int:mapid>/next', methods=['GET'])
def api_station_next(mapid):
    """Next-arrival predictions for a single parent station, used by the e-paper."""
    if not CTA_API_KEY:
        abort(500, description="Server configuration error: API key missing.")

    route = request.args.get('route')  # optional filter
    predictions = get_station_arrivals(CTA_API_KEY, mapid, route=route)

    station_name = predictions[0]['station_name'] if predictions else None
    return jsonify({
        'mapid': mapid,
        'station_name': station_name,
        'predictions': predictions,
    })


# --- Serve Frontend ---
@app.route('/')
def serve_index():
    """Serves the index.html file."""
    # Assumes index.html is in the same directory as app.py
    # For more complex apps, use Flask Blueprints and static folders
    try:
        return send_from_directory('.', 'index.html', mimetype='text/html')
    except FileNotFoundError:
        abort(404, description="index.html not found.")

# Optional: Serve other static files like CSS or JS if needed later
# @app.route('/static/<path:filename>')
# def serve_static(filename):
#     return send_from_directory('static', filename)

# --- Main Execution ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=(SITE_ENV != "production"), port=port)