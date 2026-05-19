"""
GET /stations/{station_id}/arrivals

Returns the next N CTA arrivals at a station, enriched with model delay
predictions. The station_id is the CTA parent-station mapid (e.g. 40900
for Howard on the Red Line).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import ArrivalItem, StationArrivalsResponse
from backend.collector.cta_client import CtaTrainClient
from backend.config import get_settings
from backend.ml.features import ALL_FEATURES, BOOL_FEATURES, NUMERIC_FEATURES
from backend.stations import get_station

router = APIRouter()
settings = get_settings()
_TZ = pytz.timezone("America/Chicago")


def _build_feature_row(
    eta: dict,
    station_id: str,
    db: Session,
    eta_history: list[float],
) -> dict:
    """Build a feature dict from a live CTA ETA record."""
    snap_time = datetime.now(timezone.utc)
    station = get_station(int(station_id)) if station_id.isdigit() else None
    local_dt = snap_time.astimezone(_TZ)

    minutes_until = 0.0
    if eta.get("arr_t") and eta.get("prdt"):
        minutes_until = max(
            0.0,
            (eta["arr_t"] - snap_time).total_seconds() / 60,
        )

    eta_delta_1 = None
    eta_delta_2 = None
    if len(eta_history) >= 1:
        eta_delta_1 = round(minutes_until - eta_history[-1], 3)
    if len(eta_history) >= 2:
        eta_delta_2 = round(minutes_until - eta_history[-2], 3)

    direction_code = None
    if eta.get("direction") and str(eta["direction"]).isdigit():
        direction_code = int(eta["direction"])

    return {
        "stop_sequence": station.stop_sequence if station else 0,
        "direction_code": direction_code or 0,
        "hour_of_day": local_dt.hour,
        "day_of_week": local_dt.weekday(),
        "month": local_dt.month,
        "minutes_until_arrival": minutes_until,
        "time_since_last_update_sec": (
            (snap_time - eta["prdt"]).total_seconds()
            if eta.get("prdt")
            else 0
        ),
        "eta_delta_1_min": eta_delta_1 or 0,
        "eta_delta_2_min": eta_delta_2 or 0,
        "headway_before_min": 0,
        "headway_after_min": 0,
        "is_red_line": int((eta.get("route") or "").lower() == "red"),
        "is_blue_line": int((eta.get("route") or "").lower() == "blue"),
        "is_weekend": int(local_dt.weekday() >= 5),
        "is_peak_am": int(local_dt.weekday() < 5 and 7 <= local_dt.hour < 9),
        "is_peak_pm": int(local_dt.weekday() < 5 and 16 <= local_dt.hour < 19),
        "is_scheduled": int(eta.get("is_scheduled", False)),
        "is_delayed_flag": int(eta.get("is_delayed", False)),
        "is_faulty_flag": int(eta.get("is_faulty", False)),
    }


@router.get(
    "/stations/{station_id}/arrivals",
    response_model=StationArrivalsResponse,
)
def get_station_arrivals(
    station_id: str,
    route: Optional[str] = Query(None, description="Filter by route: Red or Blue"),
    n: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    if not settings.cta_train_tracker_key:
        raise HTTPException(status_code=503, detail="CTA API key not configured")

    station = get_station(int(station_id)) if station_id.isdigit() else None
    station_name = station.name if station else station_id

    with CtaTrainClient(settings.cta_train_tracker_key) as client:
        etas = client.get_arrivals(int(station_id), max_results=n)

    if route:
        etas = [e for e in etas if (e.get("route") or "").lower() == route.lower()]

    # Pull ETA history from recent snapshots for delta features
    lookback = datetime.now(timezone.utc) - timedelta(minutes=10)
    history_rows = db.execute(
        text(
            """
            SELECT run_number, arr_t, snapshot_time
            FROM arrival_snapshots
            WHERE station_id = :sid AND snapshot_time >= :since
            ORDER BY snapshot_time DESC
            LIMIT 100
            """
        ),
        {"sid": station_id, "since": lookback},
    ).fetchall()

    eta_history_by_run: dict[str, list[float]] = {}
    for row in history_rows:
        if row.arr_t and row.snapshot_time:
            mins = max(0.0, (row.arr_t - row.snapshot_time).total_seconds() / 60)
            eta_history_by_run.setdefault(str(row.run_number), []).append(mins)

    from backend.api.main import predictor

    now = datetime.now(timezone.utc)
    arrivals: list[ArrivalItem] = []
    for eta in etas:
        run = str(eta.get("run_number") or "")
        history = eta_history_by_run.get(run, [])
        feat_row = _build_feature_row(eta, station_id, db, history)
        prediction = predictor.predict(feat_row)

        cta_eta = eta.get("arr_t")
        cta_eta_minutes = None
        if cta_eta:
            cta_eta_minutes = max(0.0, round((cta_eta - now).total_seconds() / 60, 1))

        model_delay = prediction["delay_minutes"]
        model_eta = None
        if cta_eta is not None and model_delay is not None:
            model_eta = cta_eta + timedelta(minutes=model_delay)

        arrivals.append(
            ArrivalItem(
                run_number=run,
                route=str(eta.get("route") or ""),
                direction=str(eta.get("direction") or ""),
                destination=str(eta.get("destination") or ""),
                scheduled_time=None,  # GTFS matching deferred
                cta_eta=cta_eta,
                cta_eta_minutes=cta_eta_minutes,
                model_delay_minutes=model_delay,
                model_eta=model_eta,
                delay_status=prediction["delay_status"],
                p10_minutes=prediction["p10_minutes"],
                p90_minutes=prediction["p90_minutes"],
                is_delayed=bool(eta.get("is_delayed")),
                is_scheduled=bool(eta.get("is_scheduled")),
                is_approaching=bool(eta.get("is_approaching")),
            )
        )

    return StationArrivalsResponse(
        station_id=station_id,
        station_name=station_name,
        route=route or (arrivals[0].route if arrivals else ""),
        as_of=now,
        arrivals=arrivals,
    )
