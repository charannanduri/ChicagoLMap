from __future__ import annotations  # allow `str | None` style hints on Python 3.9

import requests
import xml.etree.ElementTree as ET
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CTA_API_BASE_URL = "http://lapi.transitchicago.com/api/1.0/ttpositions.aspx"
CTA_ARRIVALS_URL = "http://lapi.transitchicago.com/api/1.0/ttarrivals.aspx"

def get_train_positions(api_key: str, route: str) -> list[dict]:
    """
    Fetches and parses train positions for a specific CTA route.

    Args:
        api_key: Your registered CTA API key.
        route: The user-friendly route identifier (e.g., 'red', 'blue', 'orange', 'purple', 'pink', 'yellow').

    Returns:
        A list of dictionaries, where each dictionary represents a train
        with 'lat', 'lon', and 'heading' keys. Returns an empty list on error.
    """
    # Map user-friendly names to the API's route identifiers and expected XML attribute names
    # Format: input_key: (api_rt_value, xml_name_value)
    route_details = {
        'red':    ('Red',  'red'),  # API uses Red, XML uses red
        'blue':   ('Blue', 'blue'), # API uses Blue, XML uses blue
        'brn':    ('Brn',  'brn'),  # API uses Brn, XML uses brn
        'brown':  ('Brn',  'brn'),
        'g':      ('G',    'g'),    # API uses G, XML uses g
        'green':  ('G',    'g'),
        'org':    ('Org',  'Org'),  # API uses Org, XML likely uses Org
        'orange': ('Org',  'Org'),
        'o':      ('Org',  'Org'),
        'p':      ('P',    'p'),    # API uses P, XML uses p
        'purple': ('P',    'p'),
        'pink':   ('Pink', 'Pink'), # API uses Pink, XML likely uses Pink
        'pnk':    ('Pink', 'Pink'),
        'y':      ('Y',    'y'),    # API uses Y, XML uses y
        'yellow': ('Y',    'y')
    }

    # Get the API route identifier and expected XML name
    input_route_lower = route.lower()
    details = route_details.get(input_route_lower)

    if not details:
        logging.error(f"Unknown or unsupported route provided: '{route}'")
        return []

    api_rt_id, xml_name_id = details # Unpack the tuple

    params = {'key': api_key, 'rt': api_rt_id} # Use the API rt value for the request
    trains = []

    try:
        response = requests.get(CTA_API_BASE_URL, params=params, timeout=10) # Added timeout
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        # Ensure content is not empty and is XML before parsing
        if not response.content or not response.headers.get('content-type', '').startswith('text/xml'):
            logging.error(f"Received non-XML or empty response for route '{route}'. Content-Type: {response.headers.get('content-type')}")
            return []

        xml_content = response.content
        logging.debug(f"Raw XML Response for route '{route}':\n{xml_content.decode('utf-8', errors='ignore')}")
        root = ET.fromstring(xml_content)

        # Check for API errors within the XML response
        error_node = root.find('err')
        if error_node is not None:
            error_msg = error_node.findtext('msg', 'Unknown API error')
            logging.error(f"CTA API Error for route '{route}': {error_msg}")
            return []

        # Find the specific route node based on the expected XML name identifier
        route_node = root.find(f".//route[@name='{xml_name_id}']")

        # If the route node doesn't exist, it means no data for this specific route (or API structure changed)
        if route_node is None:
            # Check if *any* route nodes exist to differentiate between no data and bad response
            all_route_nodes = root.findall('.//route')
            if not all_route_nodes:
                logging.warning(f"No <route> elements found in the response for route request '{route}' (API ID: '{api_rt_id}'). API might be down or response format changed.")
            else:
                # Log the names of routes that *were* found to help debug XML inconsistencies
                found_route_names = [r.get('name') for r in all_route_nodes if r.get('name')]
                logging.info(f"No data currently available for route '{route}' (API ID: '{api_rt_id}'). Route node with name '{xml_name_id}' not found in response. Found routes: {found_route_names}")
            return []

        # Find train elements *within* the specific route node
        train_nodes = route_node.findall('train')
        if not train_nodes:
            logging.info(f"No active trains found on route '{route}' (API ID: '{api_rt_id}') at this time.")
            return [] # No trains currently running on this line

        for train_node in train_nodes:
            # No need to check train_node.findtext('rt') here, as we are already inside the correct route node
            try:
                lat = float(train_node.findtext('lat'))
                lon = float(train_node.findtext('lon'))
                heading = int(train_node.findtext('heading'))
            except (ValueError, TypeError) as e:
                logging.warning(f"Could not parse lat/lon/heading for a train on route '{route}' (API ID: '{api_rt_id}'): {e}. Skipping train.")
                continue # Skip this train if core position data is invalid

            # Optional enrichment fields used by the hardware / station-status endpoints.
            # Parsed defensively — any individual field being absent or malformed
            # should not drop the whole train from the list.
            def _opt_int(tag):
                raw = train_node.findtext(tag)
                try:
                    return int(raw) if raw is not None else None
                except (ValueError, TypeError):
                    return None

            trains.append({
                'lat': lat,
                'lon': lon,
                'heading': heading,
                # Station the train is currently approaching or stopped at.
                'next_sta_id': _opt_int('nextStaId'),
                'next_sta_name': train_node.findtext('nextStaNm'),
                # isApp == 1 means the train is "approaching" (effectively at) the station.
                'is_approaching': _opt_int('isApp') == 1,
                'is_delayed': _opt_int('isDly') == 1,
                # Destination / direction signals.
                'dest_sta_id': _opt_int('destSt'),
                'dest_name': train_node.findtext('destNm'),
                # trDr is 1 or 5 depending on the line; see CTA docs.
                'direction_code': _opt_int('trDr'),
                # Predicted arrival time at nextStaId (naive local "YYYYMMDD HH:MM:SS" from the API).
                'arrival_time': train_node.findtext('arrT'),
            })

        logging.info(f"Successfully fetched {len(trains)} trains for route '{route}' (API ID: '{api_rt_id}').")

    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP request failed for route '{route}' (API ID: '{api_rt_id}'): {e}")
        return []
    except ET.ParseError as e:
        # Include part of the response for easier debugging if possible
        raw_content_snippet = response.content[:500].decode('utf-8', errors='ignore') if response and response.content else "N/A"
        logging.error(f"Failed to parse XML for route '{route}' (API ID: '{api_rt_id}'): {e}. Response snippet: {raw_content_snippet}")
        return []
    except Exception as e: # Catch any other unexpected errors
        logging.error(f"An unexpected error occurred for route '{route}' (API ID: '{api_rt_id}'): {e}")
        return []

    return trains

def get_station_arrivals(api_key: str, mapid: int, route: str | None = None, max_results: int = 4) -> list[dict]:
    """
    Fetches next-arrival predictions for a CTA parent station (mapid).

    Feeds the hardware e-paper display that shows "next train at my station".

    Args:
        api_key: Your registered CTA API key.
        mapid: CTA parent station ID (covers both directions at that station).
        route: Optional route filter (user-friendly, e.g. 'red'). When set,
               only predictions for that route are returned.
        max_results: Upper bound on predictions returned (CTA `max` param).

    Returns:
        A list of dicts with keys: route, direction_code, dest_name,
        station_name, eta_minutes, is_approaching, arrival_time. Empty list on error.
    """
    params = {'key': api_key, 'mapid': mapid, 'max': max_results}
    if route:
        # Reuse the API route-id mapping from the positions fetcher to stay consistent.
        api_rt = {
            'red': 'Red', 'blue': 'Blue', 'brn': 'Brn', 'brown': 'Brn',
            'g': 'G', 'green': 'G', 'org': 'Org', 'orange': 'Org', 'o': 'Org',
            'p': 'P', 'purple': 'P', 'pink': 'Pink', 'pnk': 'Pink',
            'y': 'Y', 'yellow': 'Y',
        }.get(route.lower())
        if api_rt:
            params['rt'] = api_rt

    predictions = []
    try:
        response = requests.get(CTA_ARRIVALS_URL, params=params, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        error_node = root.find('errCd')
        if error_node is not None and error_node.text and error_node.text != '0':
            err_msg = root.findtext('errNm', 'Unknown API error')
            logging.error(f"CTA arrivals API error for mapid={mapid}: {err_msg}")
            return []

        from datetime import datetime
        now = datetime.now()
        for eta in root.findall('eta'):
            arr_t_raw = eta.findtext('arrT')
            eta_minutes = None
            if arr_t_raw:
                try:
                    # CTA formats arrT as "YYYYMMDD HH:MM:SS" (space, not T).
                    arr_dt = datetime.strptime(arr_t_raw, "%Y%m%d %H:%M:%S")
                    eta_minutes = max(0, int((arr_dt - now).total_seconds() // 60))
                except ValueError:
                    pass
            predictions.append({
                'route': eta.findtext('rt'),
                'station_name': eta.findtext('staNm'),
                'dest_name': eta.findtext('destNm'),
                # trDr: 1 or 5; mapping to cardinal direction is route-dependent.
                'direction_code': int(eta.findtext('trDr') or 0) or None,
                'eta_minutes': eta_minutes,
                'is_approaching': eta.findtext('isApp') == '1',
                'arrival_time': arr_t_raw,
            })
    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP request failed for arrivals at mapid={mapid}: {e}")
        return []
    except ET.ParseError as e:
        logging.error(f"Failed to parse XML from arrivals endpoint for mapid={mapid}: {e}")
        return []

    return predictions


# Example usage (optional, can be run directly)
if __name__ == "__main__":
    import os
    # Get the API key from environment variable
    cta_api_key = os.environ.get("CTA_API_KEY", "")
    
    # Try to read API key from file if environment variable is not set
    if not cta_api_key and os.path.exists('api_key.txt'):
        try:
            with open('api_key.txt', 'r') as f:
                cta_api_key = f.read().strip()
            print("Successfully loaded API key from api_key.txt")
        except Exception as e:
            print(f"Error reading API key from file: {e}")

    if not cta_api_key:
        print("Please set the CTA_API_KEY environment variable or create an api_key.txt file with your CTA API key.")
    else:
        red_line_trains = get_train_positions(cta_api_key, 'red')
        if red_line_trains:
            print("\nRed Line Trains:")
            for train in red_line_trains:
                print(f"  Lat: {train['lat']}, Lon: {train['lon']}, Heading: {train['heading']}")
        else:
            print("\nCould not retrieve Red Line train data.")

        # Example for Blue line
        # blue_line_trains = get_train_positions(cta_api_key, 'blue')
        # if blue_line_trains:
        #     print("\nBlue Line Trains:")
        #     for train in blue_line_trains:
        #         print(f"  Lat: {train['lat']}, Lon: {train['lon']}, Heading: {train['heading']}") 