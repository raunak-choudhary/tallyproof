"""Typed settings for the data pipeline, loaded from the environment and ``.env``.

Nothing environment-specific is hardcoded: source URLs, paths, and resource
limits all come from here. A missing required value stops the program with the
variable's name instead of failing later in a confusing way.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class SettingsError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


class PipelineSettings(BaseSettings):
    """Settings for downloading and processing source data."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_dir: Path = Field(default=REPO_ROOT / "data", validation_alias="DATA_DIR")
    usaspending_files_url: HttpUrl = Field(validation_alias="DATA_SOURCE_USASPENDING_FILES_URL")
    usaspending_api_url: HttpUrl = Field(validation_alias="DATA_SOURCE_USASPENDING_API_URL")
    fiscaldata_api_url: HttpUrl = Field(validation_alias="DATA_SOURCE_FISCALDATA_API_URL")
    fiscal_years: list[int] = Field(default=[2025], validation_alias="DATA_FISCAL_YEARS")
    download_max_mbps: float = Field(default=20.0, gt=0, validation_alias="DATA_DOWNLOAD_MAX_MBPS")
    overlay_seed: int = Field(default=42, validation_alias="OVERLAY_SEED")
    overlay_per_anomaly: int = Field(default=25, ge=1, validation_alias="OVERLAY_PER_ANOMALY")
    replay_slice_events: int = Field(
        default=1_000_000, ge=1, validation_alias="DATA_REPLAY_SLICE_EVENTS"
    )
    replay_rate_per_sec: int = Field(
        default=2000, ge=1, validation_alias="DATA_REPLAY_RATE_PER_SEC"
    )
    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:19092", validation_alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_topic_events_raw: str = Field(
        default="fin.events.raw.v1", validation_alias="KAFKA_TOPIC_EVENTS_RAW"
    )
    # The statement is published once per business day, so checking hourly is plenty.
    treasury_poll_seconds: int = Field(
        default=3600, ge=60, validation_alias="DATA_TREASURY_POLL_SECONDS"
    )
    spark_master: str = Field(default="local[3]", validation_alias="SPARK_MASTER")
    spark_driver_memory: str = Field(default="2g", validation_alias="SPARK_DRIVER_MEMORY")
    spark_shuffle_partitions: int = Field(
        default=16, ge=1, validation_alias="SPARK_SHUFFLE_PARTITIONS"
    )

    @field_validator("data_dir")
    @classmethod
    def _anchor_relative_data_dir(cls, value: Path) -> Path:
        # Commands run from different folders (make changes into backend/), so a
        # relative DATA_DIR is anchored to the repository root, never the cwd.
        return value if value.is_absolute() else REPO_ROOT / value

    @property
    def bronze_dir(self) -> Path:
        """Untouched downloads and their manifest."""
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        """Typed, cleaned, personal-data-free Parquet."""
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        """Conformed ledger events."""
        return self.data_dir / "gold"

    @property
    def work_dir(self) -> Path:
        """Scratch space for one extracted CSV at a time."""
        return self.data_dir / "work"


@lru_cache(maxsize=1)
def get_settings() -> PipelineSettings:
    """Load settings once, failing fast with the names of any missing variables."""
    try:
        return PipelineSettings()
    except ValidationError as error:
        problems = ", ".join(
            f"{'.'.join(str(part) for part in issue['loc'])} ({issue['msg']})"
            for issue in error.errors()
        )
        raise SettingsError(
            f"Invalid or missing configuration: {problems}. See docs/configuration.md."
        ) from error
