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
