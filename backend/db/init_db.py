"""Create all tables (idempotent — safe to run multiple times)."""

from backend.db.models import Base
from backend.db.session import engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database tables created / verified.")


if __name__ == "__main__":
    init_db()
