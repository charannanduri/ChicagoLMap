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
    Text,
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
    raw_json = Column(Text)

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

    # Target (NULL for live prediction rows)
    delay_minutes = Column(Numeric(8, 2))
    delay_status = Column(String(10))  # "ahead" | "on_time" | "behind"

    __table_args__ = (
        Index("ix_mf_station_time", "station_id", "snapshot_time"),
        Index("ix_mf_route_time", "route", "snapshot_time"),
    )
