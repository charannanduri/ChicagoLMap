"""
GET /runs/{run_number}

Returns predicted arrival time and delay status at upcoming stations for
a specific train run. Uses the CTA ttfollow endpoint to get the run's
upcoming stop list, then applies the model to each stop.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import RunResponse, RunStopEstimate
from backend.collector.cta_client import CtaTrainClient
from backend.config import get_settings
from backend.stations import get_station

router = APIRouter()
settings = get_settings()

_FOLLOW_URL = "http://lapi.transitchicago.com/api/1.0/ttfollow.aspx"


@router.get("/runs/{run_number}", response_model=RunResponse)
def get_run(run_number: str, db: Session = Depends(get_db)):
    if not settings.cta_train_tracker_key:
        raise HTTPException(status_code=503, detail="CTA API key not configured")

    import httpx

    params = {
        "key": settings.cta_train_tracker_key,
        "runnumber": run_number,
        "outputType": "JSON",
    }

    try:
        resp = httpx.get(_FOLLOW_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"CTA API error: {exc}")

    ctatt = data.get("ctatt", {})
    if str(ctatt.get("errCd", "0")) != "0":
        raise HTTPException(status_code=404, detail=ctatt.get("errNm", "Run not found"))

    eta_list = ctatt.get("eta", []) or []
    if isinstance(eta_list, dict):
        eta_list = [eta_list]

    from backend.collector.cta_client import _parse_cta_dt, _flag
    from backend.api.main import predictor
    from backend.ml.serving_features import ArrivalContext, build_feature_row

    now = datetime.now(timezone.utc)
    route = None
    direction = None
    destination = None
    stops: list[RunStopEstimate] = []

    for eta in eta_list:
        route = route or eta.get("rt")
        direction = direction or eta.get("trDr")
        destination = destination or eta.get("destNm")
        station_id = str(eta.get("staId") or "")
        station = get_station(int(station_id)) if station_id.isdigit() else None

        arr_t = _parse_cta_dt(eta.get("arrT"))
        prdt = _parse_cta_dt(eta.get("prdt"))

        # Following one run gives us its whole remaining trip but no station
        # boards and no prior polls, so history and headway stay NaN.
        feat_row = build_feature_row(ArrivalContext(
            station_id=station_id,
            route=str(route or ""),
            direction=direction,
            arr_t=arr_t,
            prdt=prdt,
            is_scheduled=_flag(eta.get("isSch")),
            is_delayed=_flag(eta.get("isDly")),
            is_faulty=_flag(eta.get("isFlt")),
        ), now=now)
        prediction = predictor.predict(feat_row)

        stops.append(
            RunStopEstimate(
                station_id=station_id,
                station_name=station.name if station else eta.get("staNm"),
                stop_sequence=station.stop_sequence if station else None,
                scheduled_time=None,
                cta_eta=arr_t,
                model_delay_minutes=prediction["delay_minutes"],
                delay_status=prediction["delay_status"],
            )
        )

    return RunResponse(
        run_number=run_number,
        route=str(route or ""),
        direction=str(direction or ""),
        destination=str(destination or ""),
        as_of=now,
        stops=stops,
    )
