from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    clinical_mode_enabled: bool = False
    auth_mode: Literal["mock", "jwt"] = "jwt"
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""
    database_url: str = ""
    migration_database_url: str = ""
    session_encryption_key: str = ""
    session_ttl_minutes: int = 1440
    idempotency_ttl_minutes: int = 1440
    cors_allowed_origins: str = ""
    llm_provider: Literal["mock"] = "mock"
    embedding_provider: Literal["mock"] = "mock"
    rule_bundle_path: str = ""
    allow_external_health_data_processing: bool = False
    raw_prompt_logging: bool = False

    @property
    def is_local(self) -> bool:
        return self.app_env in ("development", "test")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _guard(self) -> Settings:
        if not self.is_local:
            if self.auth_mode == "mock":
                raise ValueError("mock auth is only permitted in development/test")
            if not self.session_encryption_key:
                raise ValueError("SESSION_ENCRYPTION_KEY is required outside development/test")
            if self.raw_prompt_logging:
                raise ValueError("RAW_PROMPT_LOGGING must stay false outside development/test")
        if self.auth_mode == "jwt" and not self.is_local:
            if not (self.auth_issuer and self.auth_audience and self.auth_jwks_url):
                raise ValueError("AUTH_ISSUER, AUTH_AUDIENCE and AUTH_JWKS_URL are required for jwt auth")
        if self.clinical_mode_enabled and not self.rule_bundle_path:
            raise ValueError("clinical mode requires RULE_BUNDLE_PATH pointing at an approved release bundle")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
