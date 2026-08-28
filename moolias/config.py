from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    base_url: str = Field(alias="MOOLIAS_BASE_URL")
    session_secret: str = Field(alias="MOOLIAS_SESSION_SECRET", min_length=32)
    cookie_secure: bool = Field(default=True, alias="MOOLIAS_COOKIE_SECURE")
    trusted_hosts: str = Field(default="*", alias="MOOLIAS_TRUSTED_HOSTS")
    access_tag: str = Field(default="", alias="MOOLIAS_ACCESS_TAG")

    mailcow_agent_url: str = Field(default="", alias="MOOLIAS_MAILCOW_AGENT_URL")
    mailcow_agent_secret: str = Field(alias="MOOLIAS_MAILCOW_AGENT_SECRET", min_length=32)

    sender_protection: bool = Field(default=False, alias="MOOLIAS_SENDER_PROTECTION")
    sender_protection_cooldown_seconds: int = Field(
        default=10,
        ge=1,
        le=300,
        alias="MOOLIAS_SENDER_PROTECTION_COOLDOWN_SECONDS",
    )

    alias_workflow_bypass_seconds: int = Field(
        default=900,
        ge=60,
        le=86400,
        alias="MOOLIAS_ALIAS_WORKFLOW_BYPASS_SECONDS",
    )
    alias_workflow_poll_seconds: int = Field(
        default=2,
        ge=1,
        le=30,
        alias="MOOLIAS_ALIAS_WORKFLOW_POLL_SECONDS",
    )
    alias_workflow_history_count: int = Field(
        default=1000,
        ge=100,
        le=10000,
        alias="MOOLIAS_ALIAS_WORKFLOW_HISTORY_COUNT",
    )
    alias_replacement_reminder_days: int = Field(
        default=7,
        ge=1,
        le=365,
        alias="MOOLIAS_ALIAS_REPLACEMENT_REMINDER_DAYS",
    )
    alias_replacement_monitoring_max_days: int = Field(
        default=30,
        ge=1,
        le=3650,
        alias="MOOLIAS_ALIAS_REPLACEMENT_MONITORING_MAX_DAYS",
    )

    newsletter_management: bool = Field(
        default=False,
        alias="MOOLIAS_NEWSLETTER_MANAGEMENT",
    )
    newsletter_tag: str = Field(
        default="moolias-newsletter",
        alias="MOOLIAS_NEWSLETTER_TAG",
    )
    newsletter_db_path: str = Field(
        default="/data/moolias-newsletters.sqlite3",
        alias="MOOLIAS_NEWSLETTER_DB_PATH",
    )
    newsletter_agent_url: str = Field(
        default="",
        alias="MOOLIAS_NEWSLETTER_AGENT_URL",
    )
    newsletter_agent_secret: str = Field(
        default="",
        alias="MOOLIAS_NEWSLETTER_AGENT_SECRET",
    )
    newsletter_poll_seconds: int = Field(
        default=60,
        ge=15,
        le=3600,
        alias="MOOLIAS_NEWSLETTER_POLL_SECONDS",
    )
    newsletter_history_count: int = Field(
        default=1000,
        ge=100,
        le=10000,
        alias="MOOLIAS_NEWSLETTER_HISTORY_COUNT",
    )

    usage_stats: bool = Field(default=False, alias="MOOLIAS_USAGE_STATS")
    usage_tag: str = Field(default="moolias-stats", alias="MOOLIAS_USAGE_TAG")
    usage_db_path: str = Field(
        default="/data/moolias-stats.sqlite3",
        alias="MOOLIAS_USAGE_DB_PATH",
    )
    usage_poll_seconds: int = Field(
        default=60,
        ge=15,
        le=3600,
        alias="MOOLIAS_USAGE_POLL_SECONDS",
    )
    usage_history_count: int = Field(
        default=1000,
        ge=100,
        le=10000,
        alias="MOOLIAS_USAGE_HISTORY_COUNT",
    )
    usage_stale_polls: int = Field(
        default=3,
        ge=1,
        le=100,
        alias="MOOLIAS_USAGE_STALE_POLLS",
    )

    mailcow_url: str = Field(alias="MAILCOW_URL")
    mailcow_internal_url: str = Field(default="", alias="MAILCOW_INTERNAL_URL")
    mailcow_api_key: str = Field(alias="MAILCOW_API_KEY", min_length=1)
    mailcow_oauth_client_id: str = Field(alias="MAILCOW_OAUTH_CLIENT_ID", min_length=1)
    mailcow_oauth_client_secret: str = Field(alias="MAILCOW_OAUTH_CLIENT_SECRET", min_length=1)
    mailcow_verify_tls: bool = Field(default=True, alias="MAILCOW_VERIFY_TLS")

    @field_validator(
        "base_url",
        "mailcow_url",
        "mailcow_internal_url",
        "mailcow_agent_url",
        "newsletter_agent_url",
    )
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator(
        "access_tag",
        "usage_tag",
        "usage_db_path",
        "mailcow_agent_secret",
        "newsletter_tag",
        "newsletter_db_path",
        "newsletter_agent_secret",
    )
    @classmethod
    def strip_optional_value(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_optional_features(self) -> "Settings":
        if not self.usage_db_path:
            raise ValueError(
                "MOOLIAS_USAGE_DB_PATH must be set because Moolias stores persistent "
                "mailbox settings there even when usage statistics are disabled"
            )
        if self.usage_stats and not self.usage_tag:
            raise ValueError("MOOLIAS_USAGE_TAG must be set when usage statistics are enabled")
        if self.newsletter_management and not self.newsletter_tag:
            raise ValueError(
                "MOOLIAS_NEWSLETTER_TAG must be set when newsletter management is enabled"
            )
        if self.newsletter_management and not self.newsletter_db_path:
            raise ValueError(
                "MOOLIAS_NEWSLETTER_DB_PATH must be set when newsletter management is enabled"
            )
        if self.newsletter_management and len(self.newsletter_agent_secret) < 32:
            raise ValueError(
                "MOOLIAS_NEWSLETTER_AGENT_SECRET must contain at least 32 characters "
                "when newsletter management is enabled"
            )
        if self.alias_replacement_monitoring_max_days < self.alias_replacement_reminder_days:
            raise ValueError(
                "MOOLIAS_ALIAS_REPLACEMENT_MONITORING_MAX_DAYS must be greater than or "
                "equal to MOOLIAS_ALIAS_REPLACEMENT_REMINDER_DAYS"
            )
        return self

    @property
    def mailcow_backend_url(self) -> str:
        return self.mailcow_internal_url or self.mailcow_url

    @property
    def oauth_callback_url(self) -> str:
        return f"{self.base_url}/oauth/callback"

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
