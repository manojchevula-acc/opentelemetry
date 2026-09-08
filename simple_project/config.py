"""App-specific config extending TelemetryConfig — only project overrides live here."""
import os
from dataclasses import dataclass, field

from beacon_kit import TelemetryConfig


@dataclass
class AppConfig(TelemetryConfig):
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
