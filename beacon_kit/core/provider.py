"""setup_telemetry() — single entry point to wire up the full OTEL stack."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator

from beacon_kit.core.exporters import build_span_exporter, build_metric_exporter

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer
    from opentelemetry.metrics import Meter
    from beacon_kit.core.config import TelemetryConfig


@dataclass
class TelemetryHandle:
    tracer: "Tracer"
    meter: "Meter"
    _tracer_provider: TracerProvider
    _meter_provider: MeterProvider

    def shutdown(self) -> None:
        self._tracer_provider.shutdown()
        self._meter_provider.shutdown()


def setup_telemetry(config: "TelemetryConfig") -> TelemetryHandle:
    resource = Resource.create(
        {
            SERVICE_NAME: config.service_name,
            SERVICE_VERSION: config.service_version,
            "deployment.environment": config.environment,
            "k8s.pod.name": config.pod,
        }
    )

    span_exporter = build_span_exporter(config)
    sampler = ParentBased(root=TraceIdRatioBased(config.sampling_rate))

    tracer_provider = TracerProvider(resource=resource, sampler=sampler)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))

    if config.enable_baggage_propagation:
        from beacon_kit.propagation.baggage import BaggageSpanProcessor
        tracer_provider.add_span_processor(BaggageSpanProcessor())

    trace.set_tracer_provider(tracer_provider)

    metric_exporter = build_metric_exporter(config)
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30_000)],
    )
    metrics.set_meter_provider(meter_provider)

    # W3C TraceContext + W3C Baggage as global propagator
    set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
    )

    tracer = trace.get_tracer(config.service_name, config.service_version)
    meter = metrics.get_meter(config.service_name, config.service_version)

    return TelemetryHandle(
        tracer=tracer,
        meter=meter,
        _tracer_provider=tracer_provider,
        _meter_provider=meter_provider,
    )
