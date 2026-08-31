"""ExporterFactory — build span and metric exporters from TelemetryConfig.

Switching backends requires only an env var change; no application code changes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.sdk.trace.export import SpanExporter, ConsoleSpanExporter
from opentelemetry.sdk.metrics.export import MetricExporter, ConsoleMetricExporter

if TYPE_CHECKING:
    from beacon_kit.core.config import TelemetryConfig


def build_span_exporter(config: "TelemetryConfig") -> SpanExporter:
    if config.exporter_type == "azure_monitor":
        try:
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
            return AzureMonitorTraceExporter(connection_string=config.azure_connection_string)
        except ImportError as exc:
            raise ImportError(
                "Install azure extras: pip install beacon_kit[azure]"
            ) from exc

    if config.exporter_type == "otel_collector":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        return OTLPSpanExporter(endpoint=config.otel_endpoint)

    # Default: console (dev)
    return ConsoleSpanExporter()


def build_metric_exporter(config: "TelemetryConfig") -> MetricExporter:
    if config.exporter_type == "azure_monitor":
        try:
            from azure.monitor.opentelemetry.exporter import AzureMonitorMetricsExporter
            return AzureMonitorMetricsExporter(connection_string=config.azure_connection_string)
        except ImportError as exc:
            raise ImportError(
                "Install azure extras: pip install beacon_kit[azure]"
            ) from exc

    if config.exporter_type == "otel_collector":
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        return OTLPMetricExporter(endpoint=config.otel_endpoint)

    return ConsoleMetricExporter()
