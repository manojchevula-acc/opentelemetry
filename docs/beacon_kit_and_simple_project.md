# beacon_kit & simple_project — Complete Reference

---

## What is `beacon_kit`?

`beacon_kit` (v0.1.0) is a **drop-in OpenTelemetry sidecar library** for Python/FastAPI projects. Its philosophy: add distributed tracing, metrics, compliance audit trails, and circuit-breaker observability to any project **via decorators only** — zero rewrites to business logic.

---

## beacon_kit Capabilities (Full Public API)

### 1. Telemetry Bootstrap — `beacon_kit/core/`

| Symbol | File | What it does |
|---|---|---|
| `TelemetryConfig` | `core/config.py` | Dataclass — all OTEL config read from env vars (`SERVICE_NAME`, `EXPORTER_TYPE`, `OTEL_SAMPLING_RATE`, etc.) |
| `TelemetryHandle` | `core/provider.py` | Holds live `tracer` + `meter` objects; has `.shutdown()` |
| `setup_telemetry(config)` | `core/provider.py` | One-call bootstrap: wires up tracer provider, meter provider, exporters, samplers, W3C propagators |

Supports 3 exporter backends: `console`, `otel_collector` (gRPC), `azure_monitor`.

**`TelemetryConfig` fields (all read from environment variables):**

| Field | Env Var | Default |
|---|---|---|
| `service_name` | `SERVICE_NAME` | `"unnamed-service"` |
| `service_version` | `SERVICE_VERSION` | `"0.0.0"` |
| `environment` | `ENVIRONMENT` | `"development"` |
| `pod` | `POD_NAME` | `""` |
| `exporter_type` | `EXPORTER_TYPE` | `"console"` |
| `otel_endpoint` | `OTEL_EXPORTER_OTLP_ENDPOINT` | `"http://localhost:4317"` |
| `azure_connection_string` | `APPLICATIONINSIGHTS_CONNECTION_STRING` | `""` |
| `sampling_rate` | `OTEL_SAMPLING_RATE` | `1.0` |
| `enable_compliance` | `ENABLE_COMPLIANCE` | `False` |
| `enable_baggage_propagation` | `ENABLE_BAGGAGE_PROPAGATION` | `True` |
| `compliance_store` | `COMPLIANCE_STORE` | `"compliance_events.jsonl"` |
| `compliance_hmac_key` | `COMPLIANCE_HMAC_KEY` | `"dev-insecure-key-change-in-prod"` |

---

### 2. Decorators — `beacon_kit/decorators/`

| Decorator | File | Line | What it does |
|---|---|---|---|
| `@traced` | `decorators/trace.py` | L54 | Wraps any sync/async function in an OTEL `INTERNAL` span |
| `@traced_node(name)` | `decorators/trace.py` | L79 | Variant specifically for LangGraph pipeline node functions |
| `@traced_tool(name)` | `decorators/tool.py` | L22 | Wraps external tool/API calls in a `CLIENT` span — records input hash + output structure (never raw values) |
| `@track_latency(name)` | `decorators/metrics.py` | L14 | Records wall-clock duration as an OTEL Histogram |
| `@count_calls(name)` | `decorators/metrics.py` | L42 | Increments an OTEL Counter on every call, with `error: True/False` label |

---

### 3. Middleware — `beacon_kit/middleware/`

| Symbol | File | Line | What it does |
|---|---|---|---|
| `TelemetryMiddleware` | `middleware/fastapi.py` | L18 | ASGI middleware — reads `X-Run-ID` header, stamps `service.name`, `pod`, `run_id` on the root span; echoes `run_id` in response headers |

---

### 4. Context Propagation — `beacon_kit/propagation/`

| Symbol | File | Line | What it does |
|---|---|---|---|
| `get_current_trace_id()` | `propagation/context.py` | L12 | Returns hex trace ID of active span |
| `get_current_span_id()` | `propagation/context.py` | L19 | Returns hex span ID of active span |
| `serialize_context()` | `propagation/context.py` | L26 | Serializes active trace context to dict — for HITL checkpoint persistence |
| `restore_context(serialized)` | `propagation/context.py` | L43 | Restores a trace context from serialized dict — reconnects async jobs to original trace |
| `inject_baggage(carrier, **kv)` | `propagation/baggage.py` | L37 | Sets W3C Baggage on outbound HTTP carrier dict |
| `set_baggage_on_current_context(**kv)` | `propagation/baggage.py` | L46 | Attaches Baggage to active context — all child spans inherit these tags |
| `extract_baggage(carrier)` | `propagation/baggage.py` | L67 | Extracts W3C Baggage from inbound carrier into plain dict |
| `BaggageSpanProcessor` | `propagation/baggage.py` | L17 | Copies all active Baggage entries onto every span automatically |

---

### 5. Compliance — `beacon_kit/compliance/`

| Symbol | File | Line | What it does |
|---|---|---|---|
| `ComplianceEvent` | `compliance/events.py` | L25 | Dataclass for 8 event types (pricing, HITL, guardrail, audit, violation) — auto-stamps trace/span IDs |
| `GuardrailEvent` | `compliance/events.py` | L49 | Dataclass for guardrail decisions (`allow/block/warn/escalate`) |
| `emit_compliance_event(event, cfg)` | `compliance/events.py` | L65 | Signs + chain-hashes + persists to JSONL (thread-safe) |
| `emit_guardrail_event(event, cfg)` | `compliance/events.py` | L86 | Persists guardrail event (no chain) |
| `compute_chain_hash(event, prev)` | `compliance/chain.py` | L14 | SHA-256 of previous hash + canonical JSON — tamper-detectable linked chain |
| `sign_event(event, key)` | `compliance/chain.py` | L20 | HMAC-SHA256 signature |
| `verify_chain(events)` | `compliance/chain.py` | L29 | Validates integrity of entire event list |

**Supported `ComplianceEvent` event types:**

- `pricing_query_started`
- `pricing_query_completed`
- `hitl_approval_requested`
- `hitl_approval_decision`
- `guardrail_triggered`
- `model_output_reviewed`
- `audit_trail_checkpoint`
- `compliance_violation_detected`

---

### 6. Circuit Breaker — `beacon_kit/circuit_breaker/`

| Symbol | File | Line | What it does |
|---|---|---|---|
| `TelemetryCircuitBreaker(name, fail_max, reset_timeout)` | `circuit_breaker/breaker.py` | L46 | Wraps `pybreaker` with OTEL gauge (`circuit_breaker.state`) and span events on state transitions; usable as a decorator |

Circuit states mapped to gauge integers: `closed → 0`, `half_open → 1`, `open → 2`.

---

### 7. Utilities — `beacon_kit/utils/`

| Symbol | File | Line | What it does |
|---|---|---|---|
| `hash_inputs(data)` | `utils/hashing.py` | L13 | SHA-256 of canonical JSON — fingerprints inputs without storing raw data |
| `summarize_output(data)` | `utils/hashing.py` | L19 | Returns structural metadata (field count, size, error flag) — never raw values |
| `scrub_pii(text)` | `utils/sanitizer.py` | L26 | Redacts Bearer tokens, API keys, IBANs, NI numbers, emails, phones, account numbers |

**`scrub_pii` patterns:**

| Pattern | Replacement |
|---|---|
| Bearer tokens | `Bearer [REDACTED]` |
| OpenAI-style API keys (`sk-...`) | `[API_KEY]` |
| IBANs (GB + most EU formats) | `[IBAN]` |
| UK National Insurance numbers | `[NI_NUMBER]` |
| Email addresses | `[EMAIL]` |
| Phone numbers (E.164 + UK/US local) | `[PHONE]` |
| 14–19 consecutive digit sequences | `[ACCOUNT_NUMBER]` |

---

## What is `simple_project`?

`simple_project` is a **demo FastAPI application** that simulates a **financial deal pricing pipeline** (treasury/capital markets domain). It demonstrates the beacon_kit sidecar pattern with minimal code changes.

**What it does:**
- Accepts `POST /query` with a `deal_id` and `query_category`
- Runs a 4-step async pipeline: validate → fetch data → compute price → emit compliance record
- Pulls simulated data from an RWA engine, deal DB, and market data feed
- Returns a pricing result with the OTEL trace ID as a business correlation key

**Directory structure:**

```
simple_project/
├── __init__.py
├── main.py                  — FastAPI app entry point
├── config.py                — AppConfig extending TelemetryConfig
├── pyproject.toml
├── agents/
│   └── pricing_agent.py     — 4-step pricing pipeline (LangGraph-style nodes)
└── tools/
    └── data_tools.py        — Async I/O tool functions (RWA engine, deal DB, market data)
```

---

## How beacon_kit is Used in simple_project

### `config.py` — Line 5

```python
from beacon_kit import TelemetryConfig

@dataclass
class AppConfig(TelemetryConfig):   # inherits all OTEL config from env vars
    max_retries: int = ...
    llm_model: str = ...
    rwa_engine_url: str = ...
```

**Why:** Inheriting `TelemetryConfig` gives `AppConfig.from_env()` for free — all OTEL settings are automatically read from environment variables. The app only declares its own extra fields on top.

---

### `main.py` — Lines 24–25, 34, 49–54, 83–103

```python
# Lines 24–25 — imports
from beacon_kit import setup_telemetry, set_baggage_on_current_context
from beacon_kit.middleware.fastapi import TelemetryMiddleware

# Line 34 — bootstrap OTEL at startup
telemetry = setup_telemetry(config)

# Lines 49–54 — add run-ID enrichment middleware
app.add_middleware(
    TelemetryMiddleware,
    run_id_header="X-Run-ID",
    service_name=config.service_name,
    pod=config.pod,
)

# Lines 83–91 — stamp business context on every child span via Baggage
_baggage_token = set_baggage_on_current_context(**{
    "query.category": request.query_category,
    "business_unit": "treasury",
    "environment": config.environment,
    "pod": config.pod,
    "component": "pricing_agent",
})

# Line 103 — detach in finally block to prevent context leak
otel_context.detach(_baggage_token)
```

**Why:**
- `setup_telemetry` is the single call that wires up the entire OTEL SDK — tracer provider, meter provider, exporters, and W3C propagators.
- `TelemetryMiddleware` stamps the `X-Run-ID` header onto the root span so every request is traceable end-to-end.
- `set_baggage_on_current_context` propagates business metadata (`business_unit`, `query.category`, etc.) to **all downstream spans automatically** — no need to pass them through function arguments.

---

### `agents/pricing_agent.py` — Lines 10–12, 28, 39, 56, 76, 87–91, 102

```python
# Lines 10–12 — imports
from beacon_kit import traced_node, get_current_trace_id
from beacon_kit.compliance import ComplianceEvent, emit_compliance_event
from beacon_kit.utils.hashing import hash_inputs

# Line 28 — validate step gets its own span
@traced_node("validate_query")
async def validate_query(state): ...

# Line 39 — data fetch step
@traced_node("fetch_deal_data")
async def fetch_deal_data(state): ...

# Line 56 — pricing computation step; also sets custom span attributes manually
@traced_node("compute_pricing")
async def compute_pricing(state):
    ...
    span.set_attribute("pricing.indicative_price", indicative_price)  # line 71
    span.set_attribute("pricing.rwa_usd", rwa_usd)                    # line 72

# Line 76 — compliance emission step
@traced_node("emit_compliance_record")
async def emit_compliance_record(state): ...

# Line 102 — use active OTEL trace ID as the business correlation key
state["run_id"] = get_current_trace_id()

# Lines 82–91 — build and emit compliance record (no raw PII)
event = ComplianceEvent(
    event_type="pricing_query_completed",
    run_id=state["run_id"],
    payload_hash=hash_inputs({"deal_id": ..., "price": ...}),
    ...
)
emit_compliance_event(event, _config)
```

**Why:**
- `@traced_node` turns each pipeline step into a named OTEL span with zero boilerplate — duration and errors are automatically observable.
- `get_current_trace_id()` threads the OTEL trace ID through the business response so operations teams can correlate a deal query to a specific distributed trace.
- `hash_inputs` ensures the compliance record proves data integrity without embedding raw financial values or PII.

---

### `tools/data_tools.py` — Lines 11–12, 15, 18, 32, 45

```python
# Lines 11–12 — imports
from beacon_kit import traced_tool
from beacon_kit.circuit_breaker import TelemetryCircuitBreaker

# Line 15 — circuit breaker: open after 3 failures, reset after 10 seconds
rwa_breaker = TelemetryCircuitBreaker(name="rwa_engine", fail_max=3, reset_timeout=10)

# Line 18 — RWA engine call: traced + circuit-breaker protected
@traced_tool("rwa_engine_lookup")
@rwa_breaker
async def rwa_engine_lookup(deal_id): ...

# Line 32 — deal DB lookup: traced
@traced_tool("deal_db_lookup")
async def deal_db_lookup(deal_id): ...

# Line 45 — market data fetch: traced
@traced_tool("market_data_fetch")
async def market_data_fetch(deal_id): ...
```

**Why:**
- `@traced_tool` records every external call as a `CLIENT` span with input hash, output structure, and latency — without leaking raw data.
- `TelemetryCircuitBreaker` prevents a flaky RWA engine from causing cascading failures. Its state transitions (`closed → open → half_open`) appear directly in the OTEL trace as span events and a gauge metric.

---

## beacon_kit Usage Summary

| beacon_kit Component | Script | Line(s) | Why Used |
|---|---|---|---|
| `TelemetryConfig` | `config.py` | 5 | Base config class; provides `from_env()` and all OTEL settings |
| `setup_telemetry` | `main.py` | 34 | One-call OTEL SDK bootstrap |
| `set_baggage_on_current_context` | `main.py` | 83 | Propagates business tags to all child spans |
| `TelemetryMiddleware` | `main.py` | 49 | Stamps run-ID and service metadata on root span |
| `traced_node` | `agents/pricing_agent.py` | 28, 39, 56, 76 | Wraps each pipeline step in a named OTEL span |
| `get_current_trace_id` | `agents/pricing_agent.py` | 102 | Surfaces OTEL trace ID as business correlation key |
| `ComplianceEvent` | `agents/pricing_agent.py` | 82 | Structured compliance record with auto trace/span IDs |
| `emit_compliance_event` | `agents/pricing_agent.py` | 91 | Persists signed, chain-hashed compliance event |
| `hash_inputs` | `agents/pricing_agent.py` | 87 | Hashes deal payload for integrity proof without raw PII |
| `traced_tool` | `tools/data_tools.py` | 18, 32, 45 | CLIENT span with input hash + output summary per tool call |
| `TelemetryCircuitBreaker` | `tools/data_tools.py` | 15 | Protects RWA engine with OTEL-observable circuit breaker |
