"""
Run the delay model inside this process instead of calling a second service.

Why this exists
---------------
The predictor used to be its own Render web service that this app called over
HTTP. That does not fit the free tier: Render's allowance is 750 instance-hours
per month across the whole account, and two services that are up at the same
time spend two of those per hour of wall clock. Because /api/trains prices
every train through the predictor and the map polls it every fifteen seconds,
"both up" was the normal state whenever anyone had the site open. The account
ran out part-way through the month and both services were suspended.

Loading the model here makes one service do the work, which halves the burn and
also removes a network hop from every poll.

Safety
------
Nothing here may take the map down. If the import fails, the artifacts are
missing, or the model cannot load, `is_ready` stays False and the caller falls
back to the HTTP predictor (or to showing the CTA's own estimate). The failure
is logged once, loudly, rather than per request.

Memory
------
The ML stack plus this app is roughly 300 MB, against 512 MB on a free
instance, so gunicorn must run a single worker. Two workers would each hold
their own copy and exhaust the instance. See the start command in render.yaml.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PREDICTOR_ROOT = Path(__file__).resolve().parent / "cta-delay-predictor"

_predictor = None
_build_row = None
_ArrivalContext = None
_load_error: str | None = None


def _load() -> None:
    """Import the predictor package and load the model artifacts, once."""
    global _predictor, _build_row, _ArrivalContext, _load_error

    if not _PREDICTOR_ROOT.is_dir():
        _load_error = f"predictor package not found at {_PREDICTOR_ROOT}"
        return

    # The predictor lives in a sibling directory rather than an installed
    # package, so its root has to be importable before `backend.*` resolves.
    if str(_PREDICTOR_ROOT) not in sys.path:
        sys.path.insert(0, str(_PREDICTOR_ROOT))

    try:
        from backend.ml.predict import DelayPredictor
        from backend.ml.serving_features import ArrivalContext, build_feature_row
    except Exception as exc:  # noqa: BLE001 — a missing dep must not kill the map
        _load_error = f"import failed: {type(exc).__name__}: {exc}"
        return

    try:
        model = DelayPredictor(model_dir=str(_PREDICTOR_ROOT / "ml_models")).load()
    except Exception as exc:  # noqa: BLE001
        _load_error = f"model load failed: {type(exc).__name__}: {exc}"
        return

    if not model.is_ready:
        _load_error = "model artifacts missing or unreadable"
        return

    _predictor = model
    _build_row = build_feature_row
    _ArrivalContext = ArrivalContext
    logger.info("In-process delay predictor ready (%s)", _PREDICTOR_ROOT / "ml_models")


def is_ready() -> bool:
    return _predictor is not None


def load_error() -> str | None:
    return _load_error


def predict_batch(items: list[dict]) -> dict[str, dict]:
    """
    Price a list of live trains, keyed by run number.

    `items` uses the same shape the HTTP /predict/batch route accepted, so the
    caller can swap between the two without reshaping its payload.
    """
    if _predictor is None or _build_row is None or _ArrivalContext is None:
        return {}

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    rows = [
        _build_row(_ArrivalContext(
            station_id=str(it.get("station_id") or ""),
            route=str(it.get("route") or ""),
            direction=it.get("direction"),
            eta_seconds=it.get("eta_seconds"),
            is_scheduled=bool(it.get("is_scheduled")),
            is_delayed=bool(it.get("is_delayed")),
        ), now=now)
        for it in items
    ]

    preds = _predictor.predict_many(rows)
    return {
        str(it.get("run_number") or ""): pred
        for it, pred in zip(items, preds)
    }


_load()
if _load_error:
    logger.warning(
        "In-process predictor unavailable (%s) — falling back to the HTTP "
        "predictor if DELAY_PREDICTOR_URL is set", _load_error,
    )
