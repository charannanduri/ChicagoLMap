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

TARGET_REGRESSION = "delay_minutes"
TARGET_CLASSIFICATION = "delay_status"

# Thresholds for label derivation
AHEAD_THRESHOLD = -1.0   # delay_minutes < this → "ahead"
BEHIND_THRESHOLD = 2.0   # delay_minutes > this → "behind"

STATUS_LABELS = ["ahead", "on_time", "behind"]
