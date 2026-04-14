# Firmware

Scaffolding for the ESP32 companion device described in
[`../docs/HARDWARE.md`](../docs/HARDWARE.md).

Nothing here talks to real hardware yet — the LED driver and e-paper library
haven't been chosen. The sketch in `redline_leds/` shows the structure:
WiFi + periodic HTTP poll + a `led_driver` abstraction whose current
implementation just `Serial.printf`s what it *would* do. Swap in the real
driver once the hardware is picked.

## Targets

- Board: **TBD** — any ESP32 variant with WiFi will work (plain ESP32, S3, C6).
- LED driver: **TBD** — WS2812B, PCA9685, TLC5947 all viable.
- E-paper: **TBD** — Waveshare 2.9" or 4.2" likely.

## Build

This is Arduino-style so you can open `redline_leds/redline_leds.ino` in the
Arduino IDE or PlatformIO. Fill in `secrets.h` (gitignored — see `.gitignore`)
before flashing:

```cpp
#define WIFI_SSID     "your-ssid"
#define WIFI_PASSWORD "your-password"
#define BACKEND_HOST  "192.168.1.42"   // host running app.py
#define BACKEND_PORT  5001
```

## What the sketch does

1. Joins WiFi.
2. Every 10s, GETs `http://<BACKEND_HOST>:<BACKEND_PORT>/api/stations/red/status`.
3. Parses the JSON into a list of (station_name, north, south) rows.
4. For each row, looks up the LED index pair in `station_map.h` and tells
   `led_driver` to set colors.
5. (TODO) Periodically GETs `/api/station/<mapid>/next?route=red` for the
   user-selected home station and pushes it to the e-paper.
