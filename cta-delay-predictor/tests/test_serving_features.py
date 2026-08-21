"""
Pin the serving feature vector to what feature_builder produces at training time.

These two used to disagree in three separate ways -- the ETA history was read
newest-first in serving but oldest-first in training, headways were hardcoded
to 0, and "unknown" was encoded as 0 rather than NaN. None of it raised an
error; the model just quietly saw different features than it was trained on.
A test is the only thing that catches that class of bug.

Run:  python -m pytest tests/ -q
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from backend.ml.features import ALL_FEATURES
from backend.ml.serving_features import (
    ArrivalContext,
    build_feature_row,
    compute_headways,
)

NOW = datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)  # 09:00 Chicago, a Friday


def _ctx(**kw) -> ArrivalContext:
    base = dict(
        station_id="40900",
        route="Red",
        direction="1",
        arr_t=NOW + timedelta(minutes=6),
        prdt=NOW - timedelta(seconds=20),
    )
    base.update(kw)
    return ArrivalContext(**base)


def test_row_covers_exactly_the_trained_feature_set():
    row = build_feature_row(_ctx(), now=NOW)
    assert set(row) == set(ALL_FEATURES), (
        "serving builds a different column set than the model was trained on"
    )


def test_eta_deltas_use_most_recent_history_last():
    """
    feature_builder appends in ascending time order and reads prev_etas[-1]
    as the immediately previous poll. Serving must use the same convention:
    with history [8, 7] and a current ETA of 6, delta_1 is -1 (versus the 7),
    not -2 (versus the 8).
    """
    row = build_feature_row(_ctx(eta_history=[8.0, 7.0]), now=NOW)
    assert row["eta_delta_1_min"] == pytest.approx(-1.0)
    assert row["eta_delta_2_min"] == pytest.approx(-2.0)


def test_absent_history_is_nan_not_zero():
    """Zero means "the ETA held steady", which is a different claim."""
    row = build_feature_row(_ctx(eta_history=[]), now=NOW)
    assert math.isnan(row["eta_delta_1_min"])
    assert math.isnan(row["eta_delta_2_min"])

    row = build_feature_row(_ctx(eta_history=[8.0]), now=NOW)
    assert row["eta_delta_1_min"] == pytest.approx(-2.0)
    assert math.isnan(row["eta_delta_2_min"])


def test_absent_headway_and_prdt_are_nan():
    row = build_feature_row(_ctx(prdt=None), now=NOW)
    assert math.isnan(row["headway_before_min"])
    assert math.isnan(row["headway_after_min"])
    assert math.isnan(row["time_since_last_update_sec"])


def test_eta_seconds_fallback_for_the_positions_feed():
    """The map's batch path has seconds-to-arrival, not an arrival timestamp."""
    row = build_feature_row(
        ArrivalContext(station_id="40900", route="Red", eta_seconds=390), now=NOW
    )
    assert row["minutes_until_arrival"] == pytest.approx(6.5)


def test_minutes_until_arrival_never_negative():
    row = build_feature_row(_ctx(arr_t=NOW - timedelta(minutes=3)), now=NOW)
    assert row["minutes_until_arrival"] == 0.0


def test_time_features_are_local_chicago_not_utc():
    """14:00 UTC is 09:00 in Chicago, on a Friday."""
    row = build_feature_row(_ctx(), now=NOW)
    assert row["hour_of_day"] == 9
    assert row["day_of_week"] == 4          # Friday
    assert row["is_weekend"] == 0


@pytest.mark.parametrize("utc_hour, chicago_hour, peak_am, peak_pm", [
    (11, 6, 0, 0),
    (12, 7, 1, 0),   # first peak-AM hour
    (13, 8, 1, 0),
    (14, 9, 0, 0),   # window is [7, 9), so 9 is deliberately outside
    (20, 15, 0, 0),
    (21, 16, 0, 1),  # first peak-PM hour
    (23, 18, 0, 1),  # last peak-PM hour -- window is [16, 19)
    (0, 19, 0, 0),   # 19:00 Chicago is the following UTC day
])
def test_peak_windows_match_feature_builder(utc_hour, chicago_hour, peak_am, peak_pm):
    """
    feature_builder uses 7 <= hour < 9 and 16 <= hour < 19, weekdays only.
    The half-open upper bounds are easy to get wrong in a reimplementation,
    so both edges are pinned here.
    """
    day = 22 if utc_hour == 0 else 21          # 00:00 UTC Sat == 19:00 CDT Fri
    when = datetime(2026, 8, day, utc_hour, tzinfo=timezone.utc)
    row = build_feature_row(_ctx(arr_t=when + timedelta(minutes=6)), now=when)
    assert row["hour_of_day"] == chicago_hour
    assert row["is_peak_am"] == peak_am
    assert row["is_peak_pm"] == peak_pm


def test_weekend_is_never_peak():
    saturday = datetime(2026, 8, 22, 13, 0, tzinfo=timezone.utc)  # 08:00 Chicago
    row = build_feature_row(_ctx(arr_t=saturday + timedelta(minutes=6)), now=saturday)
    assert row["is_weekend"] == 1
    assert row["is_peak_am"] == 0


def test_headways_group_by_direction_and_use_neighbouring_gaps():
    board = [
        ("101", "1", NOW + timedelta(minutes=2)),
        ("102", "1", NOW + timedelta(minutes=9)),
        ("103", "5", NOW + timedelta(minutes=4)),   # opposite direction
        ("104", "1", NOW + timedelta(minutes=14)),
    ]
    hw = compute_headways(board)
    assert hw["101"] == (None, 7.0)      # nothing ahead of it; 7 min to the next
    assert hw["102"] == (7.0, 5.0)
    assert hw["104"] == (5.0, None)
    assert hw["103"] == (None, None)     # alone in its direction


def test_headways_ignore_arrivals_with_no_predicted_time():
    board = [
        ("101", "1", NOW + timedelta(minutes=2)),
        ("102", "1", None),
        ("103", "1", NOW + timedelta(minutes=6)),
    ]
    hw = compute_headways(board)
    assert "102" not in hw
    assert hw["101"] == (None, 4.0)


def test_unknown_route_and_station_do_not_raise():
    row = build_feature_row(
        ArrivalContext(station_id="", route="", direction=None, eta_seconds=60),
        now=NOW,
    )
    assert row["route_code"] == -1
    assert math.isnan(row["stop_sequence"])
    assert math.isnan(row["direction_code"])
