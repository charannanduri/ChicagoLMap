"""
POST /feedback

Records crowd-sourced arrival accuracy. A rider reports how far off our
predicted arrival was for a given train/station (delta_minutes; + = later than
predicted, - = earlier). Stored in user_feedback, separate from the inferred
actual_arrivals, so it can be validated before ever influencing training.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import FeedbackRequest, FeedbackResponse
from backend.db.models import UserFeedback

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(payload: FeedbackRequest, db: Session = Depends(get_db)):
    # Clamp to a sane range so a fat-fingered stepper can't inject wild values.
    delta = max(-60.0, min(60.0, float(payload.delta_minutes)))

    row = UserFeedback(
        run_number=(payload.run_number or "")[:10] or None,
        station_id=(payload.station_id or "")[:20] or None,
        route=(payload.route or "")[:10] or None,
        predicted_delay_minutes=payload.predicted_delay_minutes,
        delta_minutes=delta,
    )
    try:
        # `default_transaction_read_only` is applied to a session when it
        # connects, so a pooled connection established while the database was
        # read-only keeps refusing writes long after the database itself is
        # writable again. Opt this transaction back into read-write first so a
        # stale connection can't silently reject the insert.
        for stmt in ("SET TRANSACTION READ WRITE", "SET LOCAL default_transaction_read_only = off"):
            try:
                db.execute(text(stmt))
            except Exception:  # noqa: BLE001 — already writable, or not permitted
                pass

        db.add(row)
        db.commit()
    except Exception as exc:  # e.g. database read-only / over quota
        db.rollback()
        logger.warning("Feedback insert failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Feedback storage unavailable: {exc}")

    return FeedbackResponse(ok=True, id=row.id)
