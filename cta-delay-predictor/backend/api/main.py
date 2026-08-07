"""
FastAPI application entry point.

Start with:
    uvicorn backend.api.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import feedback, health, runs, stations
from backend.db.init_db import init_db
from backend.ml.predict import DelayPredictor

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Module-level singleton — loaded once at startup, shared across requests
predictor = DelayPredictor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    predictor.load()
    logger.info("API ready")
    yield


_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

app = FastAPI(
    title="CTA Delay Predictor",
    description="Predicts Red and Blue Line train delays using statistical models.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["ops"])
app.include_router(stations.router, tags=["arrivals"])
app.include_router(runs.router, tags=["arrivals"])
app.include_router(feedback.router, tags=["feedback"])
