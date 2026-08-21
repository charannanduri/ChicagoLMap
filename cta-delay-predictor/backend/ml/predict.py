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

from backend.ml.features import ALL_FEATURES, STATUS_LABELS

logger = logging.getLogger(__name__)


def _default_model_dir() -> str:
    """
    Read the configured model directory, importing the settings machinery only
    if we actually need it. A caller that passes an explicit directory -- the
    map app loading this in-process, for one -- should not have to install
    pydantic-settings just to load a file from a path it already knows.
    """
    from backend.config import get_settings
    return get_settings().model_dir


class DelayPredictor:
    """
    Wraps the trained XGBoost models and exposes a single predict() call.

    NaN is passed through to the models rather than filled with 0 -- training
    uses the same convention, so an unknown feature is treated as unknown
    rather than as a confident zero. See backend/ml/serving_features.py.
    """

    def __init__(self, model_dir: str | None = None) -> None:
        self._dir = Path(model_dir) if model_dir else Path(_default_model_dir())
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

    def predict_many(self, feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Predict for many feature vectors at once.

        One DataFrame and one call per model, rather than per row — the map
        prices every train on every poll, so the per-call overhead of predict()
        would dominate at ~150 trains.
        """
        if not feature_rows:
            return []
        if not self._loaded:
            return [
                {"delay_minutes": None, "delay_status": None,
                 "p10_minutes": None, "p90_minutes": None}
                for _ in feature_rows
            ]

        df = pd.DataFrame(feature_rows).reindex(columns=ALL_FEATURES)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        delays = self._reg.predict(df)
        classes = self._cls.predict(df)
        p10s = self._p10.predict(df)
        p90s = self._p90.predict(df)

        return [
            {
                "delay_minutes": round(float(delays[i]), 2),
                "delay_status": self._inv_label.get(int(classes[i]), "on_time"),
                "p10_minutes": round(float(p10s[i]), 2),
                "p90_minutes": round(float(p90s[i]), 2),
            }
            for i in range(len(feature_rows))
        ]

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
