from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    """Yield a SQLAlchemy session; closes it when the caller is done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
