"""
Application configuration via Pydantic Settings.

All secrets come from environment variables or .env files.
NEVER hardcode credentials.

The BAA endpoint registry is loaded from configuration but enforced at the network layer.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = Field(default="development")

    # --- Database ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./hcrm.db",
    )
    database_url_audit: str = Field(
        default="sqlite+aiosqlite:///./hcrm_audit.db",
    )
    redis_url: str = Field(
        default="redis://:hcrm_redis_password@localhost:6379/0",
    )

    # --- LLM (BAA-COVERED ONLY) ---
    aws_region: str = Field(default="us-east-1")
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    llm_primary_model: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
    )

    # Azure fallback (optional, must be BAA-covered)
    azure_openai_endpoint: str | None = Field(default=None)
    azure_openai_api_key: str | None = Field(default=None)
    azure_openai_deployment: str | None = Field(default=None)
    llm_fallback_model: str | None = Field(default=None)

    # Self-hosted (optional, for air-gapped clinics)
    llm_self_hosted_endpoint: str | None = Field(default=None)
    llm_self_hosted_model: str | None = Field(default=None)

    # Cost guard
    llm_daily_cost_cap_usd: float = Field(default=50.0)
    llm_cheap_model_for_operational: str = Field(
        default="anthropic.claude-3-haiku-20240307-v1:0",
    )

    # --- Encryption ---
    encryption_kms_key_arn: str = Field(
        default="",
        description="AWS KMS key ARN for envelope encryption",
    )
    encryption_key_id: str = Field(
        default="hcrm-field-encryption-key",
    )

    # --- Messaging (BAA-COVERED) ---
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_phone_number: str = Field(default="")

    paubox_api_key: str = Field(default="")
    paubox_from_email: str = Field(default="")

    # --- Clearinghouse ---
    clearinghouse_provider: str = Field(default="change_healthcare")
    change_healthcare_api_url: str = Field(default="https://apis.changehealthcare.com")
    change_healthcare_client_id: str = Field(default="")
    change_healthcare_client_secret: str = Field(default="")

    # --- EHR ---
    fhir_base_url: str = Field(default="http://mock-fhir")

    # --- Authentication ---
    oidc_issuer_url: str = Field(default="")
    oidc_client_id: str = Field(default="hcrm-client")
    oidc_client_secret: str = Field(default="")
    mfa_required: bool = Field(default=True)
    session_timeout_minutes: int = Field(default=15)

    # --- Clinic ---
    clinic_name: str = Field(default="Example Clinic")
    clinic_timezone: str = Field(default="America/New_York")
    clinic_phone: str = Field(default="+15551234567")

    # --- Audit ---
    audit_worm_storage_path: str = Field(default="/var/lib/hcrm/audit")

    # --- Telemetry ---
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4317")
    prometheus_port: int = Field(default=9090)

    # --- Breach Detection ---
    security_officer_email: str = Field(default="security@yourclinic.com")
    alert_threshold_unusual_phi_reads_per_hour: int = Field(default=100)

    # --- State Law Compliance ---
    clinic_state: str = Field(default="NY")
    retention_years: int = Field(default=6)

    @field_validator("clinic_state")
    @classmethod
    def validate_state_code(cls, v: str) -> str:
        if len(v) != 2:
            raise ValueError("clinic_state must be a 2-letter US state code")
        return v.upper()


# Singleton
settings = Settings()
