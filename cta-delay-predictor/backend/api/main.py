"""
FastAPI application entry point.

Start with:
    uvicorn backend.api.main:app --reload --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import health, runs, stations
from backend.db.init_db import init_db
from backend.ml.predict import DelayPredictor

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CTA Delay Predictor",
    description="Predicts Red and Blue Line train delays using statistical models.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["ops"])
app.include_router(stations.router, tags=["arrivals"])
app.include_router(runs.router, tags=["arrivals"])

# Module-level singleton — loaded once at startup, shared across requests
predictor = DelayPredictor()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    predictor.load()
    logger.info("API ready")
