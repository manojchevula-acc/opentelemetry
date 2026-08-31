# beacon_kit + simple_project

`beacon_kit` is a drop-in OpenTelemetry sidecar that adds distributed tracing, metrics,
compliance events, and circuit-breaker observability to **any Python/FastAPI project**
via decorators — with zero rewrites to business logic.

## Structure

```
workspace/
├── .env                 ← environment variables (copy and edit before running)
├── beacon_kit/          ← reusable sidecar (install once, use anywhere)
└── simple_project/      ← demo consumer showing minimal integration
```

---

## Quick start

```bash
cd workspace

# Install both packages (beacon_kit with FastAPI middleware support)
pip install -e "beacon_kit[fastapi]" -e simple_project

# Edit .env if needed — defaults are set for local development with console output
# Then start the server (it loads .env automatically)
uvicorn simple_project.main:app --reload
```

Test the endpoints:

**Linux / macOS (bash):**

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-Run-ID: test-run-001" \
  -d '{"deal_id": "DEAL-42", "query_category": "standard_pricing"}'
```

**Windows (PowerShell):**

> PowerShell maps `curl` to `Invoke-WebRequest`. Use `curl.exe` or `Invoke-RestMethod` instead.

```powershell
# Health check
curl.exe http://localhost:8000/health

# Pricing query — use a variable so PowerShell doesn't mangle the JSON quotes
$body = '{"deal_id": "DEAL-42", "query_category": "standard_pricing"}'
curl.exe -X POST http://localhost:8000/query `
  -H "Content-Type: application/json" `
  -H "X-Run-ID: test-run-001" `
  -d $body

# Alternative: native PowerShell (no curl needed)
Invoke-RestMethod http://localhost:8000/health

Invoke-RestMethod -Method POST -Uri http://localhost:8000/query `
  -Headers @{"Content-Type"="application/json"; "X-Run-ID"="test-run-001"} `
  -Body '{"deal_id": "DEAL-42", "query_category": "standard_pricing"}'
```

Spans print to the console. Compliance events append to `compliance_events.jsonl`.

---

## Environment variables

All configuration is driven by `.env` in the workspace root. The file is loaded
automatically at startup via `python-dotenv` — no shell exports needed.

**For CI/CD or Kubernetes**, set the same variables as pod environment variables or
secrets — the `.env` file is ignored when the variables are already set.

### Key variables

| Variable | Default | What it controls |
|---|---|---|
| `SERVICE_NAME` | `simple-project` | Name shown in traces and dashboards |
| `SERVICE_VERSION` | `0.1.0` | Semantic version attached to every span |
| `ENVIRONMENT` | `development` | Enables/disables compliance key guard and sampling |
| `POD_NAME` | `pod1-pricing-agent` | Pod identifier stamped on every span and baggage entry |
| `EXPORTER_TYPE` | `console` | Where to send telemetry — see table below |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTEL Collector gRPC endpoint |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | _(blank)_ | Azure Monitor connection string |
| `OTEL_SAMPLING_RATE` | `1.0` | Head-based SDK sampling rate (0.0–1.0) |
| `ENABLE_COMPLIANCE` | `true` | Emit Layer 03 compliance events per pricing run |
| `COMPLIANCE_STORE` | `compliance_events.jsonl` | Local compliance event log file (dev only) |
| `COMPLIANCE_HMAC_KEY` | `dev-insecure-key-change-in-prod` | HMAC signing key — **must be changed in production** |
| `MAX_RETRIES` | `3` | External API retry limit |
| `LLM_MODEL` | `gpt-4o-mini` | Azure OpenAI model deployment name |
| `RWA_ENGINE_URL` | `http://localhost:9000` | RWA capital calculation engine base URL |

### Switching export backends

Change `EXPORTER_TYPE` in `.env` — no application code changes required:

| `EXPORTER_TYPE` | Destination |
|---|---|
| `console` | stdout — default for local development |
| `otel_collector` | OTEL Collector at `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `azure_monitor` | Azure Monitor via `APPLICATIONINSIGHTS_CONNECTION_STRING` |

To switch to Azure Monitor, update two lines in `.env`:

```
EXPORTER_TYPE=azure_monitor
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;IngestionEndpoint=...
```

### Production checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Set `COMPLIANCE_HMAC_KEY` to a cryptographically random value:
  `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Set `APPLICATIONINSIGHTS_CONNECTION_STRING` from Azure Key Vault (via CSI Secrets Store)
- [ ] Set `POD_NAME` via the Kubernetes Downward API (`fieldRef: fieldPath: metadata.name`)
- [ ] Set `EXPORTER_TYPE=azure_monitor`
- [ ] Remove `.env` from the pod filesystem — use Kubernetes secrets instead

---

## How a project adopts beacon_kit

**Step 1 — install with FastAPI support:**

```bash
pip install -e "beacon_kit[fastapi]"   # for projects using TelemetryMiddleware
pip install -e "beacon_kit[azure]"     # additionally for Azure Monitor export
```

**Step 2 — startup (main.py):**

```python
from dotenv import load_dotenv
load_dotenv()                          # load .env before config reads env vars

from beacon_kit import setup_telemetry, TelemetryConfig
from beacon_kit.middleware.fastapi import TelemetryMiddleware

config = TelemetryConfig.from_env()
telemetry = setup_telemetry(config)
app.add_middleware(TelemetryMiddleware, run_id_header="X-Run-ID",
                   service_name=config.service_name, pod=config.pod)
```

**Step 3 — attach baggage so all child spans carry mandatory tags:**

```python
from beacon_kit import set_baggage_on_current_context
from opentelemetry import context as otel_context

_token = set_baggage_on_current_context(
    **{"query.category": "pricing_decision", "business_unit": "treasury",
       "environment": config.environment, "pod": config.pod, "component": "pricing_agent"}
)
try:
    result = await run_pipeline(...)
finally:
    otel_context.detach(_token)        # always detach to avoid context leaks
```

**Step 4 — decorate existing functions (zero business logic changes):**

```python
from beacon_kit import traced_node, traced_tool

@traced_node("my_agent_step")
async def my_agent_step(state: dict) -> dict: ...

@traced_tool("rwa_engine_lookup")
async def rwa_engine_lookup(deal_id: str) -> dict: ...
```

**Step 5 — for LangGraph nodes that need config, use `init_agent()`:**

```python
# pricing_agent.py
_config = None

def init_agent(config) -> None:
    global _config
    _config = config

@traced_node("emit_compliance_record")
async def emit_compliance_record(state: dict) -> dict:  # single-arg — LangGraph compatible
    emit_compliance_event(..., _config)
    return state
```

---

## beacon_kit capabilities

| Module | What it gives you |
|---|---|
| `core/config.py` | `TelemetryConfig` — all settings from env vars; `__post_init__` guard rejects insecure HMAC key in non-dev environments |
| `core/provider.py` | `setup_telemetry()` — one-call TracerProvider + MeterProvider + W3C propagator wiring |
| `core/exporters.py` | `build_span_exporter()` / `build_metric_exporter()` — console / OTEL Collector / Azure Monitor |
| `decorators/trace.py` | `@traced`, `@traced_node` — wrap any sync or async function in an OTEL span |
| `decorators/tool.py` | `@traced_tool` — CLIENT span with input hash + output summary (no raw data stored) |
| `decorators/metrics.py` | `@track_latency`, `@count_calls` — histogram and counter metrics; both count errors via `finally` |
| `middleware/fastapi.py` | `TelemetryMiddleware` — enriches FastAPI spans with `run_id` and service tags |
| `propagation/baggage.py` | `set_baggage_on_current_context()` — attaches W3C Baggage to active async context so all child spans inherit mandatory tags; `inject_baggage()` for outbound HTTP headers |
| `propagation/context.py` | `serialize_context()` / `restore_context()` — HITL checkpoint trace continuity across async boundaries |
| `compliance/events.py` | `ComplianceEvent`, `GuardrailEvent`, `emit_compliance_event()` — append-only tamper-evident audit trail |
| `compliance/chain.py` | SHA-256 chain hashing + HMAC-SHA256 signing; `verify_chain()` for integrity checks |
| `circuit_breaker/breaker.py` | `TelemetryCircuitBreaker` — pybreaker wrapper emitting OTEL span events + state gauge; compatible with pybreaker ≥ 1.0 |
| `utils/hashing.py` | `hash_inputs()`, `summarize_output()` — privacy-safe input/output handling for spans |
| `utils/sanitizer.py` | `scrub_pii()` — strips Bearer tokens, API keys, IBANs, emails, account numbers from strings |

---

## Known defaults to override before production

| Setting | Dev default | Why it must change |
|---|---|---|
| `COMPLIANCE_HMAC_KEY` | `dev-insecure-key-change-in-prod` | Known key — compliance signatures are forgeable |
| `EXPORTER_TYPE` | `console` | Traces go to stdout instead of Azure Monitor |
| `OTEL_SAMPLING_RATE` | `1.0` | Keep all traces; tail sampling at the Collector handles production volume |
| `RWA_ENGINE_URL` | `http://localhost:9000` | Points to nothing in a real deployment |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | _(blank)_ | Required for azure_monitor exporter |
