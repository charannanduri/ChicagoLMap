"""
GET /stations/{station_id}/arrivals

Returns the next N CTA arrivals at a station, enriched with model delay
predictions. The station_id is the CTA parent-station mapid (e.g. 40900
for Howard on the Red Line).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import ArrivalItem, StationArrivalsResponse
from backend.collector.cta_client import CtaTrainClient
from backend.config import get_settings
from backend.ml.serving_features import (
    ArrivalContext,
    build_feature_row,
    compute_headways,
)
from backend.stations import get_station

router = APIRouter()
settings = get_settings()


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

    # Pull ETA history from recent snapshots for the delta features.
    # Fetched newest-first so the LIMIT keeps the most recent rows, then
    # reversed: build_feature_row expects ascending order with the most
    # recent last, matching how feature_builder computes the training label.
    lookback = datetime.now(timezone.utc) - timedelta(minutes=10)
    history_rows = db.execute(
        text(
            """
            SELECT run_number, arr_t, snapshot_time
            FROM arrival_snapshots
            WHERE station_id = :sid AND snapshot_time >= :since
            ORDER BY snapshot_time DESC
            LIMIT 600
            """
        ),
        {"sid": station_id, "since": lookback},
    ).fetchall()

    eta_history_by_run: dict[str, list[float]] = {}
    for row in reversed(history_rows):
        if row.arr_t and row.snapshot_time:
            mins = max(0.0, (row.arr_t - row.snapshot_time).total_seconds() / 60)
            eta_history_by_run.setdefault(str(row.run_number), []).append(mins)

    # Headways come straight off the live board this request already fetched.
    headways = compute_headways([
        (str(e.get("run_number") or ""), e.get("direction"), e.get("arr_t"))
        for e in etas
    ])

    from backend.api.main import predictor

    now = datetime.now(timezone.utc)
    arrivals: list[ArrivalItem] = []
    for eta in etas:
        run = str(eta.get("run_number") or "")
        hw_before, hw_after = headways.get(run, (None, None))
        feat_row = build_feature_row(ArrivalContext(
            station_id=station_id,
            route=str(eta.get("route") or ""),
            direction=eta.get("direction"),
            arr_t=eta.get("arr_t"),
            prdt=eta.get("prdt"),
            is_scheduled=bool(eta.get("is_scheduled", False)),
            is_delayed=bool(eta.get("is_delayed", False)),
            is_faulty=bool(eta.get("is_faulty", False)),
            eta_history=eta_history_by_run.get(run, []),
            headway_before=hw_before,
            headway_after=hw_after,
        ), now=now)
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
