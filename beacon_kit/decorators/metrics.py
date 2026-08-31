"""@track_latency and @count_calls — metric-emitting decorators."""
from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, TypeVar

from opentelemetry import metrics

F = TypeVar("F", bound=Callable[..., Any])


def track_latency(metric_name: str, unit: str = "ms") -> Callable[[F], F]:
    """Record a histogram of wall-clock duration in milliseconds."""
    def decorator(fn: F) -> F:
        meter = metrics.get_meter(__name__)
        histogram = meter.create_histogram(metric_name, unit=unit, description=f"Latency of {fn.__qualname__}")

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    histogram.record(round((time.perf_counter() - start) * 1000, 2))
            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    return fn(*args, **kwargs)
                finally:
                    histogram.record(round((time.perf_counter() - start) * 1000, 2))
            return sync_wrapper  # type: ignore[return-value]

    return decorator


def count_calls(
    metric_name: str,
    attributes: dict | Callable[[tuple, dict, Any], dict] | None = None,
) -> Callable[[F], F]:
    """Increment a counter on every invocation.

    *attributes* may be a static dict or a callable ``(args, kwargs, result) -> dict``
    for dynamic attribute values.
    """
    def decorator(fn: F) -> F:
        meter = metrics.get_meter(__name__)
        counter = meter.create_counter(metric_name, description=f"Call count for {fn.__qualname__}")

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                _error = False
                try:
                    result = await fn(*args, **kwargs)
                    return result
                except Exception:
                    _error = True
                    raise
                finally:
                    _static = attributes(args, kwargs) if callable(attributes) else (attributes or {})
                    counter.add(1, {**_static, "error": str(_error)})
            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                _error = False
                try:
                    result = fn(*args, **kwargs)
                    return result
                except Exception:
                    _error = True
                    raise
                finally:
                    _static = attributes(args, kwargs) if callable(attributes) else (attributes or {})
                    counter.add(1, {**_static, "error": str(_error)})
            return sync_wrapper  # type: ignore[return-value]

    return decorator
