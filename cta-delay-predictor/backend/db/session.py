from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.config import get_settings

_settings = get_settings()

_is_pooler = ":6543/" in _settings.database_url

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    # pgBouncer transaction-mode pooler (Supabase port 6543) works best with
    # NullPool or a small pool — persistent connections across requests cause
    # "prepared statement already exists" errors on transaction poolers.
    pool_size=1 if _is_pooler else 10,
    max_overflow=4 if _is_pooler else 20,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    """Yield a SQLAlchemy session; closes it when the caller is done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
