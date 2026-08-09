from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ArrivalItem(BaseModel):
    run_number: str
    route: str
    direction: Optional[str]
    destination: Optional[str]
    scheduled_time: Optional[datetime]
    cta_eta: Optional[datetime]
    cta_eta_minutes: Optional[float]
    model_delay_minutes: Optional[float]
    model_eta: Optional[datetime]
    delay_status: Optional[str]       # "ahead" | "on_time" | "behind"
    p10_minutes: Optional[float]
    p90_minutes: Optional[float]
    is_delayed: bool
    is_scheduled: bool
    is_approaching: bool


class StationArrivalsResponse(BaseModel):
    station_id: str
    station_name: Optional[str]
    route: str
    as_of: datetime
    arrivals: list[ArrivalItem]


class RunStopEstimate(BaseModel):
    station_id: str
    station_name: Optional[str]
    stop_sequence: Optional[int]
    scheduled_time: Optional[datetime]
    cta_eta: Optional[datetime]
    model_delay_minutes: Optional[float]
    delay_status: Optional[str]


class RunResponse(BaseModel):
    run_number: str
    route: Optional[str]
    direction: Optional[str]
    destination: Optional[str]
    as_of: datetime
    stops: list[RunStopEstimate]


class HealthResponse(BaseModel):
    status: str
    model_ready: bool
    db_ok: bool
    snapshot_count: int


class BatchPredictItem(BaseModel):
    """One live train, as reported by the CTA positions feed."""
    run_number: Optional[str] = None
    route: Optional[str] = None        # arrivals-style key, e.g. "Red"
    station_id: Optional[str] = None   # the train's NEXT station (mapid)
    direction: Optional[str] = None
    eta_seconds: Optional[float] = None
    is_delayed: bool = False
    is_scheduled: bool = False


class BatchPredictRequest(BaseModel):
    trains: list[BatchPredictItem]


class BatchPredictResult(BaseModel):
    run_number: Optional[str]
    delay_minutes: Optional[float]
    delay_status: Optional[str]


class BatchPredictResponse(BaseModel):
    results: list[BatchPredictResult]


class FeedbackRequest(BaseModel):
    run_number: Optional[str] = None
    station_id: Optional[str] = None
    route: Optional[str] = None
    predicted_delay_minutes: Optional[float] = None
    # Rider's correction vs our prediction, in minutes:
    # + = train arrived later than we predicted, - = earlier.
    delta_minutes: float


class FeedbackResponse(BaseModel):
    ok: bool
    id: Optional[int] = None
