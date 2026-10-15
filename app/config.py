"""Application configuration management using Pydantic Settings.

Reads configuration parameters from environment variables with sensible defaults
for development. Validates critical security constraints (such as refusing default
placeholder JWT secrets in production).
"""

from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Environment
    ENV: str = "development"
    PROJECT_NAME: str = "Production URL Shortener"
    BASE_URL: str = "http://localhost:8000"

    # PostgreSQL Database URL
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/shortener"
    TEST_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/shortener_test"

    # Redis Connection
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
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
    GEOIP_DB_PATH: Union[str, None] = None

    # Rate Limiting Defaults
    RATE_LIMIT_LOGIN_PER_MIN: int = 5
    RATE_LIMIT_REGISTER_PER_HOUR: int = 5
    RATE_LIMIT_LINK_CREATE_PER_HOUR: int = 20
    RATE_LIMIT_REDIRECT_PER_MIN: int = 300

    # CORS Allowed Origins
    CORS_ORIGINS: Union[str, List[str]] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Ensures psycopg2 driver is explicitly used with SQLAlchemy 2.x."""
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """Enforces that production deployments do NOT run with the default placeholder secret."""
        # Check if environment is production
        env = info.data.get("ENV") if info.data else None
        if env == "production" and ("insecure" in v or "change-in-production" in v or len(v) < 32):
            raise ValueError(
                "In production, JWT_SECRET must be set to a secure, random string (at least 32 characters)."
            )
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """Returns CORS origins as a list of strings."""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return ["*"]


settings = Settings()
