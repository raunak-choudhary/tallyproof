"""Typed application settings loaded from the environment and ``.env``.

Every environment-specific value comes from here: secrets, URLs, limits, and the
log's signing details. A missing required variable stops startup with its name.
Each process validates only what it uses, so the API never needs, and never
receives, the private signing key; the checkpointer reads that separately.
"""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


class AppSettings(BaseSettings):
    """Settings shared by the API and the background workers."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: SecretStr = Field(validation_alias="DJANGO_SECRET_KEY")
    debug: bool = Field(default=False, validation_alias="DJANGO_DEBUG")
    allowed_hosts: str = Field(validation_alias="DJANGO_ALLOWED_HOSTS")
    cors_allowed_origins: str = Field(default="", validation_alias="CORS_ALLOWED_ORIGINS")
    data_classification: str = Field(validation_alias="DATA_CLASSIFICATION")
    # Off for local HTTP development; on wherever the API is served over HTTPS.
    secure_ssl_redirect: bool = Field(default=False, validation_alias="DJANGO_SECURE_SSL_REDIRECT")
    hsts_seconds: int = Field(default=0, ge=0, validation_alias="DJANGO_HSTS_SECONDS")
    trusted_proxy_count: int = Field(default=0, ge=0, validation_alias="TRUSTED_PROXY_COUNT")
    api_throttle_anon_reads: str = Field(
        default="300/min",
        pattern=r"^\d+/(s|sec|m|min|h|hour|d|day)$",
        validation_alias="API_THROTTLE_ANON_READS",
    )

    db_url: SecretStr = Field(validation_alias="DB_URL")
    db_owner_url: SecretStr | None = Field(default=None, validation_alias="DB_OWNER_URL")
    db_analyst_url: SecretStr | None = Field(default=None, validation_alias="DB_ANALYST_URL")

    kafka_bootstrap_servers: str = Field(validation_alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_topic_events_raw: str = Field(
        default="fin.events.raw.v1", validation_alias="KAFKA_TOPIC_EVENTS_RAW"
    )
    kafka_topic_events_dlq: str = Field(
        default="fin.events.dlq.v1", validation_alias="KAFKA_TOPIC_EVENTS_DLQ"
    )
    kafka_consumer_group_ingest: str = Field(
        default="ingest-v1", validation_alias="KAFKA_CONSUMER_GROUP_INGEST"
    )
    ingest_max_batch: int = Field(default=500, ge=1, validation_alias="INGEST_MAX_BATCH")
    dedupe_expected_items: int = Field(
        default=1_000_000, ge=1, validation_alias="DEDUPE_EXPECTED_ITEMS"
    )
    dedupe_target_fpr: float = Field(
        default=0.001, gt=0, lt=1, validation_alias="DEDUPE_TARGET_FPR"
    )

    api_base_url: str = Field(default="http://127.0.0.1:8000", validation_alias="API_BASE_URL")
    """Where command-line tools such as ``verify_event`` reach the running API."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    log_format: Literal["json", "console"] = Field(default="json", validation_alias="LOG_FORMAT")

    redis_url: str = Field(default="redis://127.0.0.1:6379/0", validation_alias="REDIS_URL")
    kafka_topic_checkpoints: str = Field(
        default="ledger.checkpoints.v1", validation_alias="KAFKA_TOPIC_CHECKPOINTS"
    )
    kafka_schema_registry_url: str = Field(
        default="http://127.0.0.1:18081", validation_alias="KAFKA_SCHEMA_REGISTRY_URL"
    )
    kafka_topic_recon_breaks: str = Field(
        default="recon.breaks.v1", validation_alias="KAFKA_TOPIC_RECON_BREAKS"
    )
    kafka_topic_ledger_appended: str = Field(
        default="ledger.appended.v1", validation_alias="KAFKA_TOPIC_LEDGER_APPENDED"
    )
    recon_late_arrival_watermark_hours: int = Field(
        default=72, ge=1, validation_alias="RECON_LATE_ARRIVAL_WATERMARK_HOURS"
    )
    recon_amount_tolerance: Decimal = Field(
        default=Decimal("0.00"), ge=0, validation_alias="RECON_AMOUNT_TOLERANCE"
    )

    merkle_log_origin: str = Field(validation_alias="MERKLE_LOG_ORIGIN")
    merkle_batch_max_size: int = Field(default=256, ge=1, validation_alias="MERKLE_BATCH_MAX_SIZE")
    merkle_batch_max_age_ms: int = Field(
        default=2000, ge=1, validation_alias="MERKLE_BATCH_MAX_AGE_MS"
    )
    checkpoint_public_key: str = Field(validation_alias="CHECKPOINT_PUBLIC_KEY")

    @field_validator("data_classification")
    @classmethod
    def _public_data_only(cls, value: str) -> str:
        # Every endpoint is public by design, which is only safe for public,
        # PII-free data. Refuse to start with anything else (threat model).
        if value != "public-no-pii":
            raise ValueError("must be 'public-no-pii'; the API serves public data only")
        return value

    @property
    def allowed_host_list(self) -> list[str]:
        """``DJANGO_ALLOWED_HOSTS`` split on commas."""
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        """``CORS_ALLOWED_ORIGINS`` split on commas."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


class CheckpointerSettings(AppSettings):
    """Settings for the checkpointer, the only process that reads the private key."""

    checkpoint_signing_key_file: Path = Field(validation_alias="CHECKPOINT_SIGNING_KEY_FILE")
    witness_export_path: Path = Field(
        default=REPO_ROOT / "var" / "witness" / "checkpoints.jsonl",
        validation_alias="WITNESS_EXPORT_PATH",
    )
    witness_interval_seconds: int = Field(
        default=3600, ge=1, validation_alias="WITNESS_INTERVAL_SECONDS"
    )
    witness_ots_enabled: bool = Field(default=True, validation_alias="WITNESS_OTS_ENABLED")
    witness_ots_calendars: str = Field(
        default="https://a.pool.opentimestamps.org,https://b.pool.opentimestamps.org",
        validation_alias="WITNESS_OTS_CALENDARS",
    )

    @field_validator("checkpoint_signing_key_file", "witness_export_path")
    @classmethod
    def _anchor_to_repo(cls, value: Path) -> Path:
        return value if value.is_absolute() else REPO_ROOT / value

    @property
    def ots_calendar_list(self) -> list[str]:
        """``WITNESS_OTS_CALENDARS`` split on commas."""
        return [c.strip().rstrip("/") for c in self.witness_ots_calendars.split(",") if c.strip()]


def _load[T: BaseSettings](model: type[T]) -> T:
    try:
        return model()
    except ValidationError as error:
        problems = ", ".join(
            f"{'.'.join(str(p) for p in issue['loc'])} ({issue['msg']})" for issue in error.errors()
        )
        raise ConfigurationError(
            f"Invalid or missing configuration: {problems}. See docs/configuration.md."
        ) from error


@lru_cache(maxsize=1)
def app_settings() -> AppSettings:
    """Load the shared settings once."""
    return _load(AppSettings)


def checkpointer_settings() -> CheckpointerSettings:
    """Load the checkpointer's settings, including the signing key file path."""
    return _load(CheckpointerSettings)
