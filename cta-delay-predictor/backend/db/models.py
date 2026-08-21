from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ArrivalSnapshot(Base):
    """One CTA ttarrivals prediction record, stored append-only on every poll."""

    __tablename__ = "arrival_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_time = Column(DateTime(timezone=True), nullable=False)
    station_id = Column(String(20), nullable=False)  # CTA mapid (parent station)
    stop_id = Column(String(20), nullable=False)      # CTA stpid (platform-level)
    route = Column(String(10), nullable=False)        # "Red" | "Blue"
    direction = Column(String(5))                     # trDr numeric code
    run_number = Column(String(10))
    destination = Column(String(100))
    prdt = Column(DateTime(timezone=True))            # CTA prediction timestamp
    arr_t = Column(DateTime(timezone=True))           # CTA predicted arrival
    is_scheduled = Column(Boolean, default=False)
    is_delayed = Column(Boolean, default=False)
    is_faulty = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_arr_snap_station_time", "station_id", "snapshot_time"),
        Index("ix_arr_snap_run_time", "run_number", "snapshot_time"),
        Index("ix_arr_snap_route_time", "route", "snapshot_time"),
    )


class TrainPosition(Base):
    """One ttpositions record per train per poll, stored append-only."""

    __tablename__ = "train_positions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_time = Column(DateTime(timezone=True), nullable=False)
    run_number = Column(String(10), nullable=False)
    route = Column(String(10), nullable=False)
    direction = Column(String(5))
    lat = Column(Numeric(10, 7))
    lon = Column(Numeric(10, 7))
    heading = Column(Integer)
    next_station_id = Column(String(20))
    next_station_name = Column(String(100))
    is_approaching = Column(Boolean, default=False)
    is_delayed = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_train_pos_run_time", "run_number", "snapshot_time"),
        Index("ix_train_pos_route_time", "route", "snapshot_time"),
    )


# ---------------------------------------------------------------------------
# GTFS tables (loaded from CTA GTFS zip, refreshed ~weekly)
# ---------------------------------------------------------------------------


class GtfsStop(Base):
    __tablename__ = "gtfs_stops"

    stop_id = Column(String(30), primary_key=True)
    stop_name = Column(String(200))
    stop_lat = Column(Numeric(10, 7))
    stop_lon = Column(Numeric(10, 7))
    location_type = Column(Integer, default=0)
    parent_station = Column(String(30))
    wheelchair_boarding = Column(Integer, default=0)


class GtfsRoute(Base):
    __tablename__ = "gtfs_routes"

    route_id = Column(String(30), primary_key=True)
    route_short_name = Column(String(50))
    route_long_name = Column(String(200))
    route_type = Column(Integer)
    route_color = Column(String(10))


class GtfsTrip(Base):
    __tablename__ = "gtfs_trips"

    trip_id = Column(String(60), primary_key=True)
    route_id = Column(String(30), nullable=False)
    service_id = Column(String(60), nullable=False)
    direction_id = Column(Integer)
    trip_headsign = Column(String(200))
    shape_id = Column(String(60))

    __table_args__ = (
        Index("ix_gtfs_trips_route", "route_id"),
        Index("ix_gtfs_trips_service", "service_id"),
    )


class GtfsStopTime(Base):
    __tablename__ = "gtfs_stop_times"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trip_id = Column(String(60), nullable=False)
    # HH:MM:SS — may exceed 23:59:59 for overnight trips (e.g. "25:30:00")
    arrival_time = Column(String(8))
    departure_time = Column(String(8))
    stop_id = Column(String(30), nullable=False)
    stop_sequence = Column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_gtfs_stop_times_trip", "trip_id"),
        Index("ix_gtfs_stop_times_stop", "stop_id"),
        UniqueConstraint("trip_id", "stop_sequence", name="uq_stop_time_trip_seq"),
    )


class GtfsCalendar(Base):
    __tablename__ = "gtfs_calendar"

    service_id = Column(String(60), primary_key=True)
    monday = Column(Boolean)
    tuesday = Column(Boolean)
    wednesday = Column(Boolean)
    thursday = Column(Boolean)
    friday = Column(Boolean)
    saturday = Column(Boolean)
    sunday = Column(Boolean)
    start_date = Column(String(8))  # YYYYMMDD
    end_date = Column(String(8))


class GtfsCalendarDate(Base):
    __tablename__ = "gtfs_calendar_dates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_id = Column(String(60), nullable=False)
    date = Column(String(8), nullable=False)          # YYYYMMDD
    exception_type = Column(Integer, nullable=False)  # 1=added, 2=removed

    __table_args__ = (
        Index("ix_gtfs_cal_dates", "service_id", "date"),
    )


# ---------------------------------------------------------------------------
# Derived / modelling tables
# ---------------------------------------------------------------------------


class ActualArrival(Base):
    """
    Inferred actual arrival: reconstructed from consecutive arrival_snapshots
    when a train's ETA reaches zero or the run disappears from predictions.
    """

    __tablename__ = "actual_arrivals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_number = Column(String(10), nullable=False)
    route = Column(String(10), nullable=False)
    direction = Column(String(5))
    station_id = Column(String(20), nullable=False)
    scheduled_arrival_time = Column(DateTime(timezone=True))
    actual_arrival_time = Column(DateTime(timezone=True), nullable=False)
    delay_minutes = Column(Numeric(8, 2))
    source_confidence = Column(Numeric(5, 3), default=1.0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_actual_arr_station_time", "station_id", "actual_arrival_time"),
        Index("ix_actual_arr_route_time", "route", "actual_arrival_time"),
        UniqueConstraint(
            "run_number", "station_id", "actual_arrival_time",
            name="uq_actual_arrival",
        ),
    )


class ModelFeature(Base):
    """
    One row per (snapshot, run, station) with pre-computed features and
    the delay_minutes target for completed arrivals (NULL for live rows).
    """

    __tablename__ = "model_features"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_number = Column(String(10))
    route = Column(String(10), nullable=False)
    direction = Column(String(5))
    station_id = Column(String(20), nullable=False)
    station_name = Column(String(100))
    snapshot_time = Column(DateTime(timezone=True), nullable=False)

    # Static
    route_code = Column(Integer)      # 0=Red 1=Blue 2=Green 3=Brown 4=Orange 5=Purple 6=Pink 7=Yellow
    stop_sequence = Column(Integer)
    is_red_line = Column(Boolean)
    is_blue_line = Column(Boolean)
    direction_code = Column(Integer)  # raw trDr value

    # Temporal
    hour_of_day = Column(Integer)
    day_of_week = Column(Integer)   # 0=Monday … 6=Sunday
    month = Column(Integer)
    is_weekend = Column(Boolean)
    is_peak_am = Column(Boolean)    # 7–9 am weekday
    is_peak_pm = Column(Boolean)    # 4–7 pm weekday

    # Real-time
    minutes_until_arrival = Column(Numeric(8, 3))
    is_scheduled = Column(Boolean)
    is_delayed_flag = Column(Boolean)
    is_faulty_flag = Column(Boolean)
    time_since_last_update_sec = Column(Numeric(10, 2))

    # Context / headway
    eta_delta_1_min = Column(Numeric(8, 3))   # ETA change vs prev snapshot
    eta_delta_2_min = Column(Numeric(8, 3))   # ETA change vs 2 snapshots ago
    headway_before_min = Column(Numeric(8, 2))
    headway_after_min = Column(Numeric(8, 2))

    # Target v1 — actual arrival minus the nearest GTFS timetable slot.
    # Retained for comparison only. Because the timetable slot is chosen as the
    # one NEAREST the actual arrival, this is bounded by half the headway and is
    # largely noise; see cta_error_minutes below.
    delay_minutes = Column(Numeric(8, 2))
    # Bucketed from delay_minutes, so it is timetable-relative like its source.
    # Not what training reads: the classifier derives its labels from
    # cta_error_minutes at train time (see ml.features.derive_status), and the
    # delay_status the API returns is that model's output, not this column.
    delay_status = Column(String(10))  # "ahead" | "on_time" | "behind"

    # Target v2 — how wrong the CTA's own live prediction turned out to be:
    # actual_arrival_time minus the arr_t this snapshot was carrying.
    # Positive means the train arrived later than the CTA said it would.
    # This is the quantity the product actually corrects, and unlike v1 it
    # differs for every snapshot of the same arrival.
    cta_error_minutes = Column(Numeric(8, 2))

    __table_args__ = (
        Index("ix_mf_station_time", "station_id", "snapshot_time"),
        Index("ix_mf_route_time", "route", "snapshot_time"),
    )


class UserFeedback(Base):
    """
    Crowd-sourced arrival accuracy: a rider reports how far off our predicted
    arrival was (delta_minutes; + = the train arrived later than predicted,
    - = earlier). Kept separate from the inferred actual_arrivals so noisy
    input can be validated before it ever influences training.
    """

    __tablename__ = "user_feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_number = Column(String(10))
    station_id = Column(String(20))
    route = Column(String(10))
    predicted_delay_minutes = Column(Numeric(8, 2))   # our model's delay estimate at report time
    delta_minutes = Column(Numeric(8, 2), nullable=False)  # rider's correction vs our estimate
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_feedback_station_time", "station_id", "created_at"),
    )
