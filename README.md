# Chicago L Map

A real-time visualization of Chicago Transit Authority (CTA) train positions using the CTA Train Tracker API.

![Chicago L Map](https://upload.wikimedia.org/wikipedia/commons/thumb/2/24/Chicago_L_diagram_sb.svg/800px-Chicago_L_diagram_sb.svg.png)

## Features

- Real-time tracking of CTA trains on a map
- Support for all CTA 'L' train lines (Red, Blue, Green, Brown, Purple, Pink, Orange, Yellow)
- 15-second auto-refresh for latest train positions
- Interactive map with train markers

## Setup and Installation

1. Clone this repository
   ```
   git clone https://github.com/charannanduri/ChicagoLMap.git
   cd ChicagoLMap
   ```

2. Create a virtual environment and install dependencies
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Set your CTA API Key**
   
   You'll need to obtain an API key from the [CTA Developer website](https://www.transitchicago.com/developers/traintracker/).
   
   Set the API key as an environment variable:
   ```
   export CTA_API_KEY="your_api_key_here"  # On Windows: set CTA_API_KEY=your_api_key_here
   ```
   
   Alternatively, for development, you can create a `.env` file in the project root with:
   ```
   CTA_API_KEY=your_api_key_here
   ```
   (Note: The `.env` file is ignored by git for security)

4. Run the application
   ```
   python app.py
   ```

5. Open a browser and navigate to `http://127.0.0.1:5001`

## Technologies Used

- **Backend**: Flask (Python)
- **Frontend**: HTML, JavaScript, Leaflet.js
- **Data Source**: CTA Train Tracker API

## License

MIT

## Author

Charan Nanduri 