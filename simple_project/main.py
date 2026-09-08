"""simple_project — FastAPI app that uses beacon_kit as a telemetry sidecar.

Setup is 4 lines at the top of this file; everything else is normal business code.
"""
from __future__ import annotations

import contextlib
import uuid
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv

# Load .env from the workspace root before any config is read.
# Has no effect if the file is absent (safe for CI/CD where env vars are injected directly).
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from opentelemetry import context as otel_context

from beacon_kit import setup_telemetry, set_baggage_on_current_context
from beacon_kit.middleware.fastapi import TelemetryMiddleware

from simple_project.config import AppConfig
from simple_project.agents.pricing_agent import run_pricing_pipeline

# ── Telemetry setup (4 lines) ──────────────────────────────────────────────
config = AppConfig.from_env()
config.service_name = "simple-project"
config.enable_compliance = True
telemetry = setup_telemetry(config)
# ──────────────────────────────────────────────────────────────────────────


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    telemetry.shutdown()


app = FastAPI(title="Simple Project", lifespan=lifespan)

# FastAPIInstrumentor MUST be applied before TelemetryMiddleware so it creates
# the root span that TelemetryMiddleware will enrich.
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,telemetry/recent")
app.add_middleware(
    TelemetryMiddleware,
    run_id_header="X-Run-ID",
    service_name=config.service_name,
    pod=config.pod,
)


# ── API models ─────────────────────────────────────────────────────────────

class PricingRequest(BaseModel):
    deal_id: str
    query_category: str = "standard_pricing"


class PricingResponse(BaseModel):
    deal_id: str
    indicative_price: float
    run_id: str
    compliance_emitted: bool


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": config.service_name}


@app.post("/query", response_model=PricingResponse)
async def query(request: PricingRequest) -> PricingResponse:
    """Run the pricing pipeline for a deal."""
    # Attach mandatory Baggage tags to the active context so all child spans inherit them.
    # set_baggage_on_current_context returns a token that must be detached in the finally block.
    _baggage_token = set_baggage_on_current_context(
        **{
            "query.category": request.query_category,
            "business_unit": "treasury",
            "environment": config.environment,
            "pod": config.pod,
            "component": "pricing_agent",
        }
    )
    try:
        state = await run_pricing_pipeline(
            deal_id=request.deal_id,
            query_category=request.query_category,
            config=config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        otel_context.detach(_baggage_token)

    return PricingResponse(
        deal_id=state["deal_id"],
        indicative_price=state["indicative_price"],
        run_id=state["run_id"],
        compliance_emitted=state.get("compliance_emitted", False),
    )


@app.get("/telemetry/recent")
async def telemetry_recent() -> dict:
    """Return the most recent spans, metrics, and logs from the in-process buffer.

    Only populated when EXPORTER_TYPE=pretty.  Returns empty lists otherwise.
    """
    try:
        from beacon_kit.core.pretty_exporter import (
            get_buffered_traces,
            get_buffered_metrics,
            get_buffered_logs,
        )
        return {
            "traces": get_buffered_traces(),
            "metrics": get_buffered_metrics(),
            "logs": get_buffered_logs(),
        }
    except ImportError:
        return {"traces": [], "metrics": [], "logs": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("simple_project.main:app", host="0.0.0.0", port=8000, reload=True)
