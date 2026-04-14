// Red Line LED board — ESP32 firmware PoC.
//
// Polls the Flask backend every POLL_INTERVAL_MS and updates two LEDs per
// station (north / south) based on which stations currently have an
// approaching Red Line train heading that way.
//
// The LED driver and e-paper are not yet chosen, so both are stubbed with
// Serial prints. Swap in real implementations when hardware is picked —
// only the two tiny abstractions at the top need to change.

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>  // install via Library Manager: "ArduinoJson" by Benoit Blanchon

#include "station_map.h"
#include "secrets.h"  // defines WIFI_SSID, WIFI_PASSWORD, BACKEND_HOST, BACKEND_PORT

// ---------------- Config ----------------
constexpr uint32_t POLL_INTERVAL_MS = 10000;
constexpr const char* ROUTE = "red";

// Colors used for the two directions. Values are packed 0xRRGGBB; the driver
// abstraction decides how to translate that to its particular LED type.
constexpr uint32_t COLOR_NORTH   = 0xFF3030;  // bright-ish red, leaning warm
constexpr uint32_t COLOR_SOUTH   = 0xFF8020;  // red-orange so north/south are visually distinct
constexpr uint32_t COLOR_OFF     = 0x000000;

// ---------------- LED driver abstraction ----------------
// Replace the body of ledDriverSet() once hardware is chosen.
// Example plans:
//   - WS2812B via FastLED: leds[index] = CRGB(r, g, b); FastLED.show();
//   - PCA9685: set three PWM channels per LED.
namespace led_driver {
  void begin() {
    Serial.println("[led] stub driver init");
  }
  void set(int16_t index, uint32_t color) {
    if (index < 0) return;  // unassigned pad — skip silently
    Serial.printf("[led] set idx=%d color=0x%06X\n", index, color);
  }
  void show() {
    // No-op for the stub. For WS2812B this would be FastLED.show().
  }
}

// ---------------- E-paper abstraction ----------------
namespace epaper {
  void begin() {
    Serial.println("[epaper] stub driver init");
  }
  void drawNextArrival(const char* stationName, int etaMinutes, const char* destName) {
    Serial.printf("[epaper] '%s': next to %s in %d min\n",
                  stationName ? stationName : "?",
                  destName ? destName : "?",
                  etaMinutes);
  }
}

// ---------------- WiFi ----------------
static void connectWifi() {
  Serial.printf("[wifi] connecting to %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\n[wifi] connected, ip=%s\n", WiFi.localIP().toString().c_str());
}

// ---------------- Backend polling ----------------
// Clears every station's LEDs, then lights those reported occupied.
// Called on every poll so "train left" automatically turns the LED off.
static void applyStatusJson(const String& body) {
  // Generously sized to handle all 33 stations even if every one is occupied.
  StaticJsonDocument<8192> doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    Serial.printf("[poll] json parse error: %s\n", err.c_str());
    return;
  }

  // Turn everything off first. The payload only lists active stations, so
  // anything not in the payload should be dark.
  for (size_t i = 0; i < RED_LINE_STATION_COUNT; ++i) {
    led_driver::set(RED_LINE_STATIONS[i].northLed, COLOR_OFF);
    led_driver::set(RED_LINE_STATIONS[i].southLed, COLOR_OFF);
  }

  JsonArray stations = doc["stations"].as<JsonArray>();
  for (JsonObject s : stations) {
    const char* name = s["name"] | "";
    const StationLeds* mapping = findStation(name);
    if (!mapping) {
      Serial.printf("[poll] unknown station '%s' (update station_map.h)\n", name);
      continue;
    }
    if (s["north"] | false) led_driver::set(mapping->northLed, COLOR_NORTH);
    if (s["south"] | false) led_driver::set(mapping->southLed, COLOR_SOUTH);
  }
  led_driver::show();
}

static void pollStatus() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[poll] skipping, wifi down");
    return;
  }
  HTTPClient http;
  String url = String("http://") + BACKEND_HOST + ":" + String(BACKEND_PORT)
             + "/api/stations/" + ROUTE + "/status";
  http.begin(url);
  http.setTimeout(5000);
  int code = http.GET();
  if (code == 200) {
    applyStatusJson(http.getString());
  } else {
    Serial.printf("[poll] HTTP %d from %s\n", code, url.c_str());
  }
  http.end();
}

// TODO: plumb a configured mapid in from the backend (e.g. via /api/config/epaper-station).
// For now this is a compile-time constant so the call pattern is in place.
constexpr int EPAPER_MAPID = 0;  // 0 == disabled; set to a real Red Line mapid to enable.

static void pollEpaper() {
  if (EPAPER_MAPID == 0) return;
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  String url = String("http://") + BACKEND_HOST + ":" + String(BACKEND_PORT)
             + "/api/station/" + String(EPAPER_MAPID) + "/next?route=" + ROUTE;
  http.begin(url);
  http.setTimeout(5000);
  int code = http.GET();
  if (code == 200) {
    StaticJsonDocument<2048> doc;
    if (!deserializeJson(doc, http.getString())) {
      const char* stationName = doc["station_name"] | "";
      JsonArray preds = doc["predictions"].as<JsonArray>();
      if (preds.size() > 0) {
        JsonObject p = preds[0];
        epaper::drawNextArrival(stationName,
                                p["eta_minutes"] | -1,
                                p["dest_name"] | "");
      }
    }
  }
  http.end();
}

// ---------------- Arduino entry points ----------------
void setup() {
  Serial.begin(115200);
  delay(200);
  led_driver::begin();
  epaper::begin();
  connectWifi();
}

void loop() {
  static uint32_t lastPoll = 0;
  uint32_t now = millis();
  if (now - lastPoll >= POLL_INTERVAL_MS) {
    lastPoll = now;
    pollStatus();
    pollEpaper();
  }
  delay(50);
}
