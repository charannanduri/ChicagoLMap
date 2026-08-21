"""
The one place a feature vector is built for a live prediction.

There were three copies of this — in the station-arrivals route, the batch
predict route, and (by import) the run-follow route — and they had already
drifted apart. Two of them zeroed features the third computed, and the one
that computed them was reading its ETA history in the wrong order. Three
copies is *how* train/serve skew happens, so there is now one.

Missing values are NaN, not 0. Zero is a claim ("the ETA has not moved",
"the trains are simultaneous"); NaN is the absence of one. XGBoost learns a
default split direction for NaN, so telling it the truth is strictly better
than telling it a confident falsehood. Training uses the same convention.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytz

from backend.ml.features import ROUTE_CODE
from backend.stations import get_station

_TZ = pytz.timezone("America/Chicago")

NAN = float("nan")


@dataclass
class ArrivalContext:
    """Everything known about one predicted arrival at prediction time."""

    station_id: str = ""
    route: str = ""
    direction: str | None = None
    arr_t: datetime | None = None
    prdt: datetime | None = None
    is_scheduled: bool = False
    is_delayed: bool = False
    is_faulty: bool = False

    # Prior ETAs for this (run, station), ascending — most recent LAST, which
    # is the order feature_builder uses when it computes the training labels.
    eta_history: list[float] = field(default_factory=list)

    # Gap in minutes to the train ahead of / behind this one at the same
    # station and direction. None when the station board does not show one.
    headway_before: float | None = None
    headway_after: float | None = None

    # Used when arr_t is absent (the positions feed carries seconds, not a time).
    eta_seconds: float | None = None


def _num(value: float | None) -> float:
    return NAN if value is None else float(value)


def build_feature_row(ctx: ArrivalContext, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    local_dt = now.astimezone(_TZ)
    station = get_station(int(ctx.station_id)) if ctx.station_id.isdigit() else None
    route = ctx.route or ""

    if ctx.arr_t is not None:
        minutes_until = max(0.0, (ctx.arr_t - now).total_seconds() / 60)
    elif ctx.eta_seconds is not None:
        minutes_until = max(0.0, ctx.eta_seconds / 60.0)
    else:
        minutes_until = NAN

    # Same arithmetic as feature_builder: delta against the immediately
    # previous poll, then the one before that.
    eta_delta_1 = NAN
    eta_delta_2 = NAN
    if not math.isnan(minutes_until):
        if len(ctx.eta_history) >= 1:
            eta_delta_1 = round(minutes_until - ctx.eta_history[-1], 3)
        if len(ctx.eta_history) >= 2:
            eta_delta_2 = round(minutes_until - ctx.eta_history[-2], 3)

    direction_code = NAN
    if ctx.direction is not None and str(ctx.direction).isdigit():
        direction_code = int(ctx.direction)

    return {
        "route_code": ROUTE_CODE.get(route, -1),
        "stop_sequence": station.stop_sequence if station else NAN,
        "direction_code": direction_code,
        "hour_of_day": local_dt.hour,
        "day_of_week": local_dt.weekday(),
        "month": local_dt.month,
        "minutes_until_arrival": minutes_until,
        "time_since_last_update_sec": (
            round((now - ctx.prdt).total_seconds(), 2) if ctx.prdt else NAN
        ),
        "eta_delta_1_min": eta_delta_1,
        "eta_delta_2_min": eta_delta_2,
        "headway_before_min": _num(ctx.headway_before),
        "headway_after_min": _num(ctx.headway_after),
        "is_red_line": int(route.lower() == "red"),
        "is_blue_line": int(route.lower() == "blue"),
        "is_weekend": int(local_dt.weekday() >= 5),
        "is_peak_am": int(local_dt.weekday() < 5 and 7 <= local_dt.hour < 9),
        "is_peak_pm": int(local_dt.weekday() < 5 and 16 <= local_dt.hour < 19),
        "is_scheduled": int(bool(ctx.is_scheduled)),
        "is_delayed_flag": int(bool(ctx.is_delayed)),
        "is_faulty_flag": int(bool(ctx.is_faulty)),
    }


def compute_headways(
    board: list[tuple[str, str | None, datetime | None]],
) -> dict[str, tuple[float | None, float | None]]:
    """
    Gap to the train ahead and behind, for every arrival on a station board.

    `board` is [(run_number, direction, arr_t), ...] as returned live by
    ttarrivals for one station. Mirrors feature_builder's headway_lookup:
    group by direction, sort by predicted arrival, take neighbouring gaps.

    Returns {run_number: (headway_before_min, headway_after_min)}.
    """
    by_direction: dict[str, list[tuple[datetime, str]]] = {}
    for run, direction, arr_t in board:
        if arr_t is None:
            continue
        by_direction.setdefault(str(direction or ""), []).append((arr_t, run))

    out: dict[str, tuple[float | None, float | None]] = {}
    for entries in by_direction.values():
        entries.sort(key=lambda e: e[0])
        for i, (arr_t, run) in enumerate(entries):
            before = (
                round((arr_t - entries[i - 1][0]).total_seconds() / 60, 2)
                if i > 0 else None
            )
            after = (
                round((entries[i + 1][0] - arr_t).total_seconds() / 60, 2)
                if i < len(entries) - 1 else None
            )
            out[run] = (before, after)
    return out
