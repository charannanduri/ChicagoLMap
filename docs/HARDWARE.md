# Hardware Companion Device — Design Notes

This document tracks the long-term plan to turn the CTA-Visualizer website into
a physical wall-mounted board: a PCB etched with the Chicago 'L' map, where each
station has addressable RGB LEDs that light up when a train is present, plus an
e-paper display that shows the next arrival time at a station the user picks
from the website.

Status: **design / scaffolding only**. No hardware selected yet.

---

## Goal

A physical ambient display of the CTA system. At a glance you can see every
train currently moving on the L, and the e-paper tells you when the next train
arrives at your "home" station.

## Hardware Concept

| Component           | Role                                                        | Chosen? |
| ------------------- | ----------------------------------------------------------- | ------- |
| ESP32               | WiFi MCU, polls backend, drives LEDs + e-paper              | No — specific variant TBD (ESP32-S3 / ESP32-C6 / plain ESP32 all candidates) |
| LED driver(s)       | Drives N RGB LEDs (2 per station × ~144 stations ≈ 300 LEDs) | No — candidates: WS2812B daisy chain, PCA9685+discrete RGBs, TLC5947 |
| RGB LEDs            | Two per station, one per direction served at that station    | No — likely whatever matches the driver choice |
| E-paper display     | Next-arrival time for user-selected station                 | No — candidates: Waveshare 2.9" / 4.2" |
| PCB                 | Custom board with L-map silkscreen and per-station LED pads | Not fabricated |

Counts to keep in mind when sizing drivers:
- 8 Red Line stations handled by the PoC — 16 LEDs.
- ~144 stations total across all lines — ~288 LEDs for the full build
  (confirmed by the KMZ: 144 placemarks).

## Why Two LEDs Per Station

Every 'L' station serves two directions of travel along a given line. Example:
Clark/Division (Red Line) serves northbound trains (toward Howard) and
southbound trains (toward 95th/Dan Ryan). At a transfer station the same
"station" can sit on multiple lines, but on each individual line there are
still exactly two directions. Representing direction physically lets you see
a wave of trains moving through the system.

For stations served by multiple lines (e.g. Fullerton = Red + Brown + Purple),
the PoC will treat each line independently — so Fullerton has 6 LEDs total
(2 × 3 lines). We may revisit this grouping later; it's possible to collapse
to per-direction regardless of line using the CTA's `mapid` concept.

## Data Flow

```
CTA Train Tracker API
        │
        ▼
  Flask backend  (existing)
   /api/trains/<route>              ← website marker layer
   /api/geojson/stops/<route>       ← website stops layer
   /api/stations/<route>/status     ← NEW: compact, per-station occupancy for the ESP32
   /api/station/<mapid>/next        ← NEW: next-arrival predictions for the e-paper
        │
        ▼
     ESP32 (WiFi)
        │
        ├─► LED driver → 2 RGB LEDs per station
        └─► E-paper display (next-arrival at user-selected station)
```

The ESP32 is a thin client. All the CTA API complexity (auth, XML parsing,
route-name inconsistencies, filtering) stays in the Flask backend so we don't
re-implement it in embedded C.

## Backend Endpoints

### Existing

- `GET /api/trains/<route>` — list of live train positions (lat/lon/heading).
  Originally designed for the web map; we're augmenting the dicts with
  `next_sta_id`, `next_sta_name`, `is_app`, `dest_name`, `dest_sta_id`,
  `direction_code`, `arr_t` so that we can tell which station each train is
  at/approaching and in which direction.

### Planned (PoC)

- `GET /api/stations/<route>/status` — one entry per station on the route:
  ```json
  {
    "route": "red",
    "as_of": "2026-04-13T20:00:00Z",
    "stations": [
      {
        "name": "Clark/Division",
        "north": true,
        "south": false
      },
      ...
    ]
  }
  ```
  A direction is `true` when there's a Red Line train currently approaching
  (`isApp == 1`) or already at that station in that direction. The ESP32
  consumes this every ~10s and just walks the list setting LEDs.

- `GET /api/station/<mapid>/next?route=red` — next-arrival predictions for the
  e-paper display at the user-selected station:
  ```json
  {
    "station_name": "Clark/Division",
    "predictions": [
      {"direction": "north", "dest": "Howard", "eta_minutes": 3, "is_approaching": false},
      {"direction": "south", "dest": "95th/Dan Ryan", "eta_minutes": 7, "is_approaching": false}
    ]
  }
  ```
  Backed by CTA's `ttarrivals.aspx?mapid=...`.

### Planned (later)

- `GET /api/config/epaper-station` / `POST /api/config/epaper-station` — store
  the user's chosen station across page loads (persistence layer TBD — even a
  flat JSON file is fine to start).

## Rate-Limit / Polling Budget

CTA Train Tracker allows up to 100,000 requests/day per key. Our design:

- One `ttpositions.aspx?rt=red` call per poll feeds the whole status endpoint.
- One `ttarrivals.aspx?mapid=X` call per poll feeds the e-paper endpoint.
- At a 10s poll interval that's 2 × 6 × 60 × 24 = **17,280 req/day**. Headroom
  to go per-line (×8 = ~70k) without blowing the budget.
- Backend should cache the raw API response for ~5s so multiple ESP32s polling
  at once don't amplify calls to the CTA.

## Firmware

Scaffolding lives in `firmware/redline_leds/`. It's an Arduino-style
`.ino` sketch that:

1. Joins WiFi,
2. Every 10s GETs `/api/stations/red/status`,
3. Walks `stations[]` and for each station looks up the LED index pair
   (north, south) in a local `station_map.h`,
4. Sets those LEDs' colors via a driver abstraction that currently just prints
   to serial (swap in real driver code once hardware is chosen),
5. Periodically GETs `/api/station/<mapid>/next` for the configured station
   and redraws the e-paper (stubbed — real driver TBD).

## Open Questions / TODO

- [ ] Pick an ESP32 variant (S3 with PSRAM if we end up with a heavy e-paper
      library; plain ESP32 otherwise).
- [ ] Pick an LED driver strategy. WS2812B addressable is simplest wiring-wise
      but has per-LED timing constraints; PCA9685 is easier on MCU but needs
      more I²C wiring.
- [ ] Pick an e-paper size + driver library.
- [ ] Map every station's `mapid` → (north_led_index, south_led_index). For the
      PoC we do this by name matching against the KMZ placemarks.
- [ ] Decide how to handle transfer stations where one physical station is on
      multiple lines (share LEDs? one set per line?).
- [ ] Persistence for the "my station" e-paper choice (SQLite or a JSON file).
- [ ] Power budget for 300 RGB LEDs at worst-case brightness.
- [ ] Enclosure / front panel material (acrylic with rear-printed map?).
- [ ] OTA firmware updates over the Flask backend (nice-to-have).

## Non-Goals (for now)

- Full 8-line support — Red Line only until the pipeline is proven.
- Bus tracker integration — trains only.
- Historical data / timelapse mode — live only.
