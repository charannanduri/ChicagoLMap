"""
Prediction service — loads trained model artifacts and produces delay
estimates for a feature vector dict.

The predictor is instantiated once at API startup (see api/main.py) and
reused across requests.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from backend.config import get_settings
from backend.ml.features import ALL_FEATURES, STATUS_LABELS

logger = logging.getLogger(__name__)

settings = get_settings()


class DelayPredictor:
    """Wraps the trained XGBoost models and exposes a single predict() call."""

    def __init__(self, model_dir: str | None = None) -> None:
        self._dir = Path(model_dir or settings.model_dir)
        self._reg = None
        self._cls = None
        self._p10 = None
        self._p90 = None
        self._label_map: dict[str, int] = {}
        self._inv_label: dict[int, str] = {}
        self._loaded = False

    def load(self) -> "DelayPredictor":
        """Load model artifacts from disk. Call once at startup."""
        try:
            self._reg = joblib.load(self._dir / "xgb_regressor.joblib")
            self._cls = joblib.load(self._dir / "xgb_classifier.joblib")
            self._p10 = joblib.load(self._dir / "xgb_p10.joblib")
            self._p90 = joblib.load(self._dir / "xgb_p90.joblib")
            self._label_map = joblib.load(self._dir / "label_map.joblib")
            self._inv_label = {v: k for k, v in self._label_map.items()}
            self._loaded = True
            logger.info("Delay predictor loaded from %s", self._dir)
        except FileNotFoundError as exc:
            logger.warning("Model artifacts not found (%s) — predictions will be null", exc)
        return self

    @property
    def is_ready(self) -> bool:
        return self._loaded

    def predict(self, feature_row: dict[str, Any]) -> dict[str, Any]:
        """
        Predict delay for one feature vector.

        Returns:
            {
                "delay_minutes": float | None,
                "delay_status":  "ahead" | "on_time" | "behind" | None,
                "p10_minutes":   float | None,
                "p90_minutes":   float | None,
            }
        """
        if not self._loaded:
            return {
                "delay_minutes": None,
                "delay_status": None,
                "p10_minutes": None,
                "p90_minutes": None,
            }

        df = pd.DataFrame([feature_row]).reindex(columns=ALL_FEATURES)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.fillna(0)

        delay = float(self._reg.predict(df)[0])
        cls_idx = int(self._cls.predict(df)[0])
        status = self._inv_label.get(cls_idx, "on_time")
        p10 = float(self._p10.predict(df)[0])
        p90 = float(self._p90.predict(df)[0])

        return {
            "delay_minutes": round(delay, 2),
            "delay_status": status,
            "p10_minutes": round(p10, 2),
            "p90_minutes": round(p90, 2),
        }
