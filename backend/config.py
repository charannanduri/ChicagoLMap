from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    cta_train_tracker_key: str = ""
    database_url: str = "postgresql://postgres:postgres@localhost:5432/cta_delays"
    poll_interval_seconds: int = 25
    gtfs_url: str = "https://www.transitchicago.com/downloads/sch_data/google_transit.zip"
    model_dir: str = "ml_models"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
