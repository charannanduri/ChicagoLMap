import requests
import xml.etree.ElementTree as ET
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CTA_API_BASE_URL = "http://lapi.transitchicago.com/api/1.0/ttpositions.aspx"

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
                trains.append({'lat': lat, 'lon': lon, 'heading': heading})
            except (ValueError, TypeError) as e:
                logging.warning(f"Could not parse data for a train on route '{route}' (API ID: '{api_rt_id}'): {e}. Skipping train.")
                continue # Skip this train if data is invalid

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