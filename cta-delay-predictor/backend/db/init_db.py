"""Create all tables (idempotent — safe to run multiple times)."""

from sqlalchemy import text

from backend.db.models import Base
from backend.db.session import engine

_MIGRATIONS = [
    # Add route_code to model_features so all 8 lines are distinguishable by XGBoost
    """
    ALTER TABLE model_features
        ADD COLUMN IF NOT EXISTS route_code INTEGER;
    """,
    """
    UPDATE model_features SET route_code = CASE
        WHEN route = 'Red'  THEN 0
        WHEN route = 'Blue' THEN 1
        WHEN route = 'G'    THEN 2
        WHEN route = 'Brn'  THEN 3
        WHEN route = 'Org'  THEN 4
        WHEN route = 'P'    THEN 5
        WHEN route = 'Pink' THEN 6
        WHEN route = 'Y'    THEN 7
        ELSE -1
    END
    WHERE route_code IS NULL;
    """,
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for sql in _MIGRATIONS:
            conn.execute(text(sql))
    print("Database tables created / verified.")


if __name__ == "__main__":
    init_db()
