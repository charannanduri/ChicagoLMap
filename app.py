from __future__ import annotations  # allow `str | None` style hints on Python 3.9

import os
import logging
import json # Added for loading GeoJSON
import zipfile # For reading KMZ
from io import BytesIO # For reading zip content in memory
from flask import Flask, jsonify, abort, send_from_directory, request
from cta_data import get_train_positions, get_station_arrivals # Import our data fetching functions
from fastkml import kml # KML parsing library
from fastkml.features import Placemark # Placemark lives here in fastkml >= 1.0
from shapely.geometry import mapping # To convert geometry to GeoJSON compatible format
from bs4 import BeautifulSoup # Added HTML parser

# Configure basic logging (optional, but good practice)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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
    logging.warning("CTA API Key not found. Please set the CTA_API_KEY environment variable or create an api_key.txt file.")
    # You might want to exit or handle this more gracefully depending on requirements
    # For now, we'll allow the app to run but API calls will likely fail.

# Allowed routes (you can expand this list)
# Using a set for efficient lookup
ALLOWED_ROUTES = {"red", "blue", "g", "brn", "p", "y", "pnk", "o"}

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
                    feature = {
                        "type": "Feature",
                        "geometry": geojson_geometry,
                        "properties": {
                            "name": station_name,
                            "address": address,  # Add address to properties
                            "route": route_value  # Add route to properties
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

    # get_train_positions handles its own logging for fetch errors
    # We return the data (which might be an empty list if fetching failed)
    return jsonify({"route": route_lower, "trains": train_data})

# --- GeoJSON API Routes --- (Updated)
@app.route('/api/geojson/routes/<route>', methods=['GET'])
def api_get_geojson_route(route):
    """Serves GeoJSON linestring for a specific route. (Placeholder - KMZ not provided for lines)"""
    logging.warning(f"Route line geometry requested for '{route}', but only KMZ stops provided. Returning empty.")
    # Return empty FeatureCollection as we don't have line data source
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

    from datetime import datetime, timezone
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
    # Runs the development server. For production, use a proper WSGI server like Gunicorn.
    app.run(debug=True, port=5001) # Using port 5001 to avoid conflicts if 5000 is common 