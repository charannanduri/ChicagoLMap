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
        route: The route identifier (e.g., 'red', 'blue', 'g', 'brn').

    Returns:
        A list of dictionaries, where each dictionary represents a train
        with 'lat', 'lon', and 'heading' keys. Returns an empty list on error.
    """
    params = {'key': api_key, 'rt': route}
    trains = []

    try:
        response = requests.get(CTA_API_BASE_URL, params=params, timeout=10) # Added timeout
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        # Ensure content is not empty and is XML before parsing
        if not response.content or not response.headers.get('content-type', '').startswith('text/xml'):
            logging.error(f"Received non-XML or empty response for route '{route}'. Content-Type: {response.headers.get('content-type')}")
            return []

        xml_content = response.content
        root = ET.fromstring(xml_content)

        # Check for API errors within the XML response
        error_node = root.find('err')
        if error_node is not None:
            error_msg = error_node.findtext('msg', 'Unknown API error')
            logging.error(f"CTA API Error for route '{route}': {error_msg}")
            return []

        # Find all train elements within the specified route
        # The structure is <ctatt><route name='...'><train>...</train></route></ctatt>
        route_node = root.find(f".//route[@name='{route}']")
        if route_node is None:
            # It's possible the API returns an empty <ctatt> if the key is valid but no trains are running/found for that route.
            # Let's check if any route node exists at all.
            all_route_nodes = root.findall('.//route')
            if not all_route_nodes:
                logging.warning(f"No <route> elements found in the response for route '{route}'.")
            else:
                logging.warning(f"Route node for '{route}' specifically not found, though other routes might exist.")
            return [] # Return empty list if the specific route node isn't found

        for train_node in route_node.findall('train'):
            try:
                lat = float(train_node.findtext('lat'))
                lon = float(train_node.findtext('lon'))
                heading = int(train_node.findtext('heading'))
                # You could extract more info here, e.g., run number ('rn'), destination ('destNm')
                trains.append({'lat': lat, 'lon': lon, 'heading': heading})
            except (ValueError, TypeError) as e:
                logging.warning(f"Could not parse data for a train on route '{route}': {e}. Skipping train.")
                continue # Skip this train if data is invalid

    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP request failed for route '{route}': {e}")
        return []
    except ET.ParseError as e:
        logging.error(f"Failed to parse XML for route '{route}': {e}")
        return []
    except Exception as e: # Catch any other unexpected errors
        logging.error(f"An unexpected error occurred for route '{route}': {e}")
        return []

    logging.info(f"Successfully fetched {len(trains)} trains for route '{route}'.")
    return trains

# Example usage (optional, can be run directly)
if __name__ == "__main__":
    import os
    # Get the API key from environment variable
    cta_api_key = os.environ.get("CTA_API_KEY", "")

    if not cta_api_key:
        print("Please set the CTA_API_KEY environment variable with your CTA API key.")
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