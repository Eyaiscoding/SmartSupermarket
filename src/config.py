"""
Application configuration.
===========================
Centralised settings for the B2G backend, loaded from environment variables
with sensible defaults for local development.
"""

from __future__ import annotations

import os


class Settings:
    """Application settings loaded from environment variables."""

    # -- Ingestion mode: "csv" (default, tests) or "mqtt" (live demo) --
    INGESTION_MODE: str = os.getenv("B2G_INGESTION_MODE", "csv")

    # -- CSV settings --
    DATASET_PATH: str = os.getenv("B2G_DATASET_PATH", "")

    # -- MQTT settings --
    MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    MQTT_TOPIC: str = os.getenv("MQTT_TOPIC", "supermarket/telemetry")
    MQTT_CLIENT_ID: str = os.getenv("MQTT_CLIENT_ID", "b2g-ingestion")

    # -- TimescaleDB settings --
    TIMESCALE_HOST: str = os.getenv("TIMESCALE_HOST", "localhost")
    TIMESCALE_PORT: int = int(os.getenv("TIMESCALE_PORT", "5432"))
    TIMESCALE_DB: str = os.getenv("TIMESCALE_DB", "b2g")
    TIMESCALE_USER: str = os.getenv("TIMESCALE_USER", "b2g")
    TIMESCALE_PASSWORD: str = os.getenv("TIMESCALE_PASSWORD", "b2g_password")

    @property
    def timescale_url(self) -> str:
        return (
            f"postgresql://{self.TIMESCALE_USER}:{self.TIMESCALE_PASSWORD}"
            f"@{self.TIMESCALE_HOST}:{self.TIMESCALE_PORT}/{self.TIMESCALE_DB}"
        )

    # -- Redis settings --
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()
