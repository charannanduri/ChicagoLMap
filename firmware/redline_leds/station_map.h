// Red Line station -> LED index map.
//
// Each station has two LEDs on the PCB:
//   - northbound (toward Howard)
//   - southbound (toward 95th/Dan Ryan)
//
// LED indices are whatever the LED driver addresses — if using a WS2812B
// strip they're positions along the chain; if using PCA9685 they're channel
// numbers. The driver abstraction just takes an int.
//
// Station names must match exactly the `nextStaNm` values returned by the CTA
// ttpositions API (which is what the backend echoes in /api/stations/red/status).
// Canonical list from the CTA rail stations KMZ.
//
// TODO: fill in the actual LED indices once the PCB layout is done. Using
// -1 for unassigned so the driver abstraction can skip them safely.

#pragma once

#include <Arduino.h>

struct StationLeds {
  const char* name;
  int16_t northLed;  // -1 if unassigned
  int16_t southLed;
};

// Red Line stations, ordered north -> south.
constexpr StationLeds RED_LINE_STATIONS[] = {
  {"Howard",              -1, -1},
  {"Jarvis",              -1, -1},
  {"Morse",               -1, -1},
  {"Loyola",              -1, -1},
  {"Granville",           -1, -1},
  {"Thorndale",           -1, -1},
  {"Bryn Mawr",           -1, -1},
  {"Berwyn",              -1, -1},
  {"Argyle",              -1, -1},
  {"Lawrence",            -1, -1},
  {"Wilson",              -1, -1},
  {"Sheridan",            -1, -1},
  {"Addison",             -1, -1},
  {"Belmont",             -1, -1},
  {"Fullerton",           -1, -1},
  {"North/Clybourn",      -1, -1},
  {"Clark/Division",      -1, -1},
  {"Chicago",             -1, -1},
  {"Grand",               -1, -1},
  {"Lake",                -1, -1},
  {"Monroe",              -1, -1},
  {"Jackson",             -1, -1},
  {"Harrison",            -1, -1},
  {"Roosevelt",           -1, -1},
  {"Cermak-Chinatown",    -1, -1},
  {"Sox-35th",            -1, -1},
  {"47th",                -1, -1},
  {"Garfield",            -1, -1},
  {"63rd",                -1, -1},
  {"69th",                -1, -1},
  {"79th",                -1, -1},
  {"87th",                -1, -1},
  {"95th/Dan Ryan",       -1, -1},
};

constexpr size_t RED_LINE_STATION_COUNT =
    sizeof(RED_LINE_STATIONS) / sizeof(RED_LINE_STATIONS[0]);

// Linear-scan lookup by station name. The list is small (33 entries), so this
// is fine — no need for a hashmap. Returns nullptr on miss.
inline const StationLeds* findStation(const char* name) {
  for (size_t i = 0; i < RED_LINE_STATION_COUNT; ++i) {
    if (strcmp(RED_LINE_STATIONS[i].name, name) == 0) {
      return &RED_LINE_STATIONS[i];
    }
  }
  return nullptr;
}
