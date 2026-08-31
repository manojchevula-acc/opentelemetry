"""beacon_kit — drop-in OpenTelemetry sidecar.

Import the pieces you need. Typical minimal setup:

    from beacon_kit import setup_telemetry, TelemetryConfig
    from beacon_kit.middleware.fastapi import TelemetryMiddleware
    from beacon_kit.decorators import traced_node, traced_tool

    config = TelemetryConfig.from_env()
    telemetry = setup_telemetry(config)
"""
from beacon_kit.core.config import TelemetryConfig
from beacon_kit.core.provider import TelemetryHandle, setup_telemetry
from beacon_kit.decorators.trace import traced, traced_node
from beacon_kit.decorators.tool import traced_tool
from beacon_kit.decorators.metrics import track_latency, count_calls
from beacon_kit.propagation.context import (
    get_current_trace_id,
    get_current_span_id,
    serialize_context,
    restore_context,
)
from beacon_kit.propagation.baggage import inject_baggage, extract_baggage, set_baggage_on_current_context
from beacon_kit.utils.hashing import hash_inputs, summarize_output
from beacon_kit.utils.sanitizer import scrub_pii

__all__ = [
    # Core
    "TelemetryConfig",
    "TelemetryHandle",
    "setup_telemetry",
    # Decorators
    "traced",
    "traced_node",
    "traced_tool",
    "track_latency",
    "count_calls",
    # Propagation helpers
    "get_current_trace_id",
    "get_current_span_id",
    "serialize_context",
    "restore_context",
    "inject_baggage",
    "extract_baggage",
    "set_baggage_on_current_context",
    # Utils
    "hash_inputs",
    "summarize_output",
    "scrub_pii",
]

__version__ = "0.1.0"
