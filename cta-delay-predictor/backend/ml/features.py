"""
Feature column definitions shared between training and prediction.
"""
from __future__ import annotations

# Maps CTA route string → stable integer code for XGBoost feature
ROUTE_CODE: dict[str, int] = {
    "Red": 0, "Blue": 1, "G": 2, "Brn": 3,
    "Org": 4, "P": 5, "Pink": 6, "Y": 7,
}

# Numeric features fed to the model
NUMERIC_FEATURES = [
    "route_code",
    "stop_sequence",
    "direction_code",
    "hour_of_day",
    "day_of_week",
    "month",
    "minutes_until_arrival",
    "time_since_last_update_sec",
    "eta_delta_1_min",
    "eta_delta_2_min",
    "headway_before_min",
    "headway_after_min",
]

# Boolean features (stored as 0/1 after fillna)
BOOL_FEATURES = [
    "is_red_line",
    "is_blue_line",
    "is_weekend",
    "is_peak_am",
    "is_peak_pm",
    "is_scheduled",
    "is_delayed_flag",
    "is_faulty_flag",
]

ALL_FEATURES = NUMERIC_FEATURES + BOOL_FEATURES

# What the model predicts: how wrong the CTA's own live estimate turns out to
# be, in minutes, positive meaning the train arrived later than the CTA said.
#
# This replaced delay_minutes (actual arrival minus the nearest GTFS timetable
# slot). That label was chosen by nearest-neighbour matching, so it was bounded
# by half the headway and largely noise -- a train twelve minutes late got
# matched to a different train's slot and labelled roughly on time. Measured
# against "trust the CTA exactly", a model on the old target had no skill;
# on this one it has ~20% with serve-time features only.
#
# It also fixes a reference-frame error. The prediction is added to the CTA's
# live estimate, so the target has to be measured against that same estimate.
# A timetable-relative delay added to a live ETA was mixing two clocks.
TARGET_REGRESSION = "cta_error_minutes"

# Errors beyond this are almost always a mis-joined arrival rather than a real
# CTA miss; a handful of them would otherwise dominate the loss.
TARGET_CLIP_MIN = 20.0

# Retained for comparison only -- see ModelFeature.delay_minutes.
LEGACY_TARGET_REGRESSION = "delay_minutes"

# Thresholds for label derivation, in minutes of CTA error. Derived at train
# time rather than stored, so changing them does not need a migration and a
# backfill of eight hundred thousand rows.
AHEAD_THRESHOLD = -1.0   # arriving more than a minute sooner than the CTA says
BEHIND_THRESHOLD = 2.0   # arriving more than two minutes later than it says

STATUS_LABELS = ["ahead", "on_time", "behind"]


def derive_status(error_minutes: float | None) -> str | None:
    """
    Bucket a CTA error into the three labels the API and clients already use.

    The strings are unchanged so existing clients keep working; what they mean
    has shifted from "versus the timetable" to "versus the CTA's own estimate",
    which is the comparison a rider looking at the CTA's number actually cares
    about.
    """
    if error_minutes is None:
        return None
    if error_minutes < AHEAD_THRESHOLD:
        return "ahead"
    if error_minutes <= BEHIND_THRESHOLD:
        return "on_time"
    return "behind"
