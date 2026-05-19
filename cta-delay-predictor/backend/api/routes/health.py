from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.api.deps import get_db
from backend.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    db_ok = False
    snapshot_count = 0
    try:
        row = db.execute(text("SELECT COUNT(*) FROM arrival_snapshots")).scalar()
        snapshot_count = int(row or 0)
        db_ok = True
    except Exception:
        pass

    from backend.api.main import predictor
    return HealthResponse(
        status="ok",
        model_ready=predictor.is_ready,
        db_ok=db_ok,
        snapshot_count=snapshot_count,
    )
