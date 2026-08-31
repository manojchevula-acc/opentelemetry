"""App-specific config extending TelemetryConfig — only project overrides live here."""
import os
from dataclasses import dataclass, field

from beacon_kit import TelemetryConfig


@dataclass
class AppConfig(TelemetryConfig):
    # App-specific settings layered on top of the telemetry config
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    rwa_engine_url: str = field(
        default_factory=lambda: os.getenv("RWA_ENGINE_URL", "http://localhost:9000")
    )
