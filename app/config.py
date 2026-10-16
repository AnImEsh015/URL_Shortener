"""Application configuration management using Pydantic Settings.

Reads configuration parameters from environment variables with sensible defaults
for development. Validates critical security constraints (such as refusing default
placeholder JWT secrets in production) and normalizes database and cache URLs.
"""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Environment
    ENV: str = "development"
    PROJECT_NAME: str = "Production URL Shortener"
    BASE_URL: str = "http://localhost:8000"

    # PostgreSQL Database URL
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/shortener"
    TEST_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/shortener_test"

    # Redis Connection (Supports redis:// and rediss:// TLS URLs)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery Configuration (Optional; derived from REDIS_URL if not provided)
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    CELERY_ALWAYS_EAGER: bool = False

    # Security & JWT Configuration
    JWT_SECRET: str = "insecure-dev-secret-change-in-production-1234567890"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    IP_HASH_SALT: str = "dev-salt-change-in-production-abcdef123456"

    # Network, Proxy, & Validation Flags
    TRUSTED_PROXY: bool = False
    REJECT_PRIVATE_IPS: bool = True
    CACHE_ENABLED: bool = True

    # Optional GeoIP Database Path
    GEOIP_DB_PATH: str | None = None

    # Rate Limiting Defaults
    RATE_LIMIT_LOGIN_PER_MIN: int = 5
    RATE_LIMIT_REGISTER_PER_HOUR: int = 5
    RATE_LIMIT_LINK_CREATE_PER_HOUR: int = 20
    RATE_LIMIT_REDIRECT_PER_MIN: int = 300

    # CORS Allowed Origins
    CORS_ORIGINS: str | list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Normalizes Render's postgres:// or standard postgresql:// to postgresql+psycopg2://."""
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg2://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """Enforces that production deployments do NOT run with the default placeholder secret."""
        env = info.data.get("ENV") if info.data else None
        if env == "production" and ("insecure" in v or "change-in-production" in v or len(v) < 32):
            raise ValueError(
                "In production, JWT_SECRET must be set to a secure, random string (at least 32 characters)."
            )
        return v

    @model_validator(mode="after")
    def derive_redis_and_celery_urls(self) -> "Settings":
        """Derives Celery broker and result backend URLs from REDIS_URL when unspecified."""
        import os

        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL

        # Automatic fallback for BASE_URL on Render if not manually overridden to a custom domain
        render_external_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_external_url and ("localhost" in self.BASE_URL or "url-shortener.onrender.com" in self.BASE_URL):
            self.BASE_URL = render_external_url.rstrip("/")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        """Returns CORS origins as a list of strings, auto-prepending https/http for bare domains."""
        if isinstance(self.CORS_ORIGINS, list):
            raw = self.CORS_ORIGINS
        elif isinstance(self.CORS_ORIGINS, str):
            raw = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        else:
            raw = ["*"]

        origins = []
        for o in raw:
            origins.append(o)
            if o != "*" and not o.startswith(("http://", "https://")):
                origins.append(f"https://{o}")
                origins.append(f"http://{o}")
        return origins


settings = Settings()
