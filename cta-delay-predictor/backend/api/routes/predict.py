"""
POST /predict/batch

Prices every live train on the map in a single call. The map polls positions
every 15 seconds and animates each train toward its next stop using our
predicted arrival — so this has to price ~150 trains per poll, which rules out
one request (or one model call) per train.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytz
from fastapi import APIRouter

from backend.api.schemas import (
    BatchPredictItem,
    BatchPredictRequest,
    BatchPredictResponse,
    BatchPredictResult,
)
from backend.ml.features import ROUTE_CODE
from backend.stations import get_station

logger = logging.getLogger(__name__)
router = APIRouter()

_TZ = pytz.timezone("America/Chicago")


def _feature_row(item: BatchPredictItem, local_dt: datetime) -> dict:
    """
    Build a model feature vector from a live position record.

    Mirrors the station-arrivals feature builder, minus the per-run ETA history
    (the positions feed carries no prior ETAs). Those deltas default to 0, which
    is what the model already sees for a train it is meeting for the first time.
    """
    station_id = item.station_id or ""
    station = get_station(int(station_id)) if station_id.isdigit() else None
    route = item.route or ""
    minutes_until = max(0.0, (item.eta_seconds or 0) / 60.0)
    direction_code = int(item.direction) if item.direction and str(item.direction).isdigit() else 0

    return {
        "route_code": ROUTE_CODE.get(route, -1),
        "stop_sequence": station.stop_sequence if station else 0,
        "direction_code": direction_code,
        "hour_of_day": local_dt.hour,
        "day_of_week": local_dt.weekday(),
        "month": local_dt.month,
        "minutes_until_arrival": minutes_until,
        "time_since_last_update_sec": 0,
        "eta_delta_1_min": 0,
        "eta_delta_2_min": 0,
        "headway_before_min": 0,
        "headway_after_min": 0,
        "is_red_line": int(route.lower() == "red"),
        "is_blue_line": int(route.lower() == "blue"),
        "is_weekend": int(local_dt.weekday() >= 5),
        "is_peak_am": int(local_dt.weekday() < 5 and 7 <= local_dt.hour < 9),
        "is_peak_pm": int(local_dt.weekday() < 5 and 16 <= local_dt.hour < 19),
        "is_scheduled": int(item.is_scheduled),
        "is_delayed_flag": int(item.is_delayed),
        "is_faulty_flag": 0,
    }


@router.post("/predict/batch", response_model=BatchPredictResponse)
def predict_batch(payload: BatchPredictRequest):
    from backend.api.main import predictor

    items = payload.trains[:400]  # generous ceiling; the whole system is ~200 trains
    if not items:
        return BatchPredictResponse(results=[])

    local_dt = datetime.now(timezone.utc).astimezone(_TZ)
    rows = [_feature_row(item, local_dt) for item in items]
    predictions = predictor.predict_many(rows)

    return BatchPredictResponse(results=[
        BatchPredictResult(
            run_number=item.run_number,
            delay_minutes=pred["delay_minutes"],
            delay_status=pred["delay_status"],
        )
        for item, pred in zip(items, predictions)
    ])
