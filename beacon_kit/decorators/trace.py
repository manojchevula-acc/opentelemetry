"""@traced and @traced_node decorators — wrap any function in an OTEL span."""
from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, TypeVar, overload

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

F = TypeVar("F", bound=Callable[..., Any])


def _make_traced_wrapper(fn: F, span_name: str, attributes: dict, kind: SpanKind) -> F:
    tracer = trace.get_tracer(__name__)

    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(span_name, kind=kind) as span:
                for k, v in attributes.items():
                    span.set_attribute(k, v)
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    # ERROR status only for unexpected infrastructure failures, not business errors
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    raise
        return async_wrapper  # type: ignore[return-value]
    else:
        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(span_name, kind=kind) as span:
                for k, v in attributes.items():
                    span.set_attribute(k, v)
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    raise
        return sync_wrapper  # type: ignore[return-value]


@overload
def traced(fn: F) -> F: ...
@overload
def traced(
    *, name: str | None = None, attributes: dict | None = None, kind: SpanKind = SpanKind.INTERNAL
) -> Callable[[F], F]: ...


def traced(  # type: ignore[misc]
    fn: F | None = None,
    *,
    name: str | None = None,
    attributes: dict | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> F | Callable[[F], F]:
    """Wrap a function in a child OTEL span.

    Usage:
        @traced
        def my_func(): ...

        @traced(name="custom.span", attributes={"key": "value"})
        async def my_async_func(): ...
    """
    def decorator(f: F) -> F:
        span_name = name or f.__qualname__
        return _make_traced_wrapper(f, span_name, attributes or {}, kind)

    if fn is not None:
        return decorator(fn)
    return decorator


def traced_node(name: str, attributes: dict | None = None) -> Callable[[F], F]:
    """Decorator for LangGraph node functions — INTERNAL span kind, node name as span name."""
    def decorator(fn: F) -> F:
        return _make_traced_wrapper(fn, name, attributes or {}, SpanKind.INTERNAL)
    return decorator
