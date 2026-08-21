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

from fastapi import APIRouter

from backend.api.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    BatchPredictResult,
)
from backend.ml.serving_features import ArrivalContext, build_feature_row

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/predict/batch", response_model=BatchPredictResponse)
def predict_batch(payload: BatchPredictRequest):
    from backend.api.main import predictor

    items = payload.trains[:400]  # generous ceiling; the whole system is ~200 trains
    if not items:
        return BatchPredictResponse(results=[])

    # The positions feed carries no prior ETAs and no station board, so the
    # history and headway features stay NaN here rather than 0 — the model is
    # told it does not know, not told the trains are evenly spaced.
    now = datetime.now(timezone.utc)
    rows = [
        build_feature_row(ArrivalContext(
            station_id=item.station_id or "",
            route=item.route or "",
            direction=item.direction,
            eta_seconds=item.eta_seconds,
            is_scheduled=bool(item.is_scheduled),
            is_delayed=bool(item.is_delayed),
        ), now=now)
        for item in items
    ]
    predictions = predictor.predict_many(rows)

    return BatchPredictResponse(results=[
        BatchPredictResult(
            run_number=item.run_number,
            delay_minutes=pred["delay_minutes"],
            delay_status=pred["delay_status"],
        )
        for item, pred in zip(items, predictions)
    ])
