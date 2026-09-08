"""Pricing agent — LangGraph-style node functions decorated with beacon_kit.

Each node function is untouched business logic; the only addition is
@traced_node from beacon_kit at the top of each function.
"""
from __future__ import annotations

from opentelemetry import trace

from beacon_kit import (
    traced_node,
    traced_pipeline,
    log_calls,
    get_current_trace_id,
    track_latency,
    count_calls,
)
from beacon_kit.compliance import ComplianceEvent, emit_compliance_event
from beacon_kit.utils.hashing import hash_inputs

from simple_project.tools.data_tools import rwa_engine_lookup, deal_db_lookup, market_data_fetch

# Module-level config reference set once at startup via init_agent().
# Avoids passing config as a second argument to node functions, which is
# incompatible with LangGraph's single-argument node calling convention.
_config = None


def init_agent(config) -> None:
    """Register the app config so node functions can access it without a parameter."""
    global _config
    _config = config


@traced_node("validate_query", state_attributes=["deal_id", "query_category"])
async def validate_query(state: dict) -> dict:
    """Validate that required fields are present in the query state."""
    required = {"deal_id", "query_category"}
    missing = required - state.keys()
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    state["validated"] = True
    return state


@traced_node("fetch_deal_data", state_attributes=["deal_id"])
async def fetch_deal_data(state: dict) -> dict:
    """Fetch all required data for the deal in parallel."""
    deal_id = state["deal_id"]

    import asyncio
    rwa, deal, market = await asyncio.gather(
        rwa_engine_lookup(deal_id),
        deal_db_lookup(deal_id),
        market_data_fetch(state.get("asset_class", "credit")),
    )
    state["rwa"] = rwa
    state["deal"] = deal
    state["market"] = market
    return state


@traced_node("compute_pricing", state_attributes=["query_category"])
@track_latency("gernas.pricing.compute_latency_ms", unit="ms", attribute_keys=["query_category"])
async def compute_pricing(state: dict) -> dict:
    """Compute the indicative price from fetched data."""
    rwa_usd = state["rwa"]["rwa_usd"]
    rate = state["market"]["rate"]
    notional = state["deal"]["notional"]

    indicative_price = round((rwa_usd * rate) / notional, 6)
    state["indicative_price"] = indicative_price
    state["pricing_complete"] = True

    # Enrich the current span with a business outcome attribute
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("pricing.indicative_price", indicative_price)
        span.set_attribute("pricing.rwa_usd", rwa_usd)

    return state


@traced_node("emit_compliance_record", state_attributes=["deal_id", "query_category"])
async def emit_compliance_record(state: dict) -> dict:
    """Emit a compliance event after pricing is computed — separate from OTEL pipeline."""
    if not _config or not _config.enable_compliance:
        return state

    event = ComplianceEvent(
        event_type="pricing_query_completed",
        run_id=state.get("run_id", "unknown"),
        actor="pricing_agent",
        outcome="success" if state.get("pricing_complete") else "partial",
        payload_hash=hash_inputs(
            {"deal_id": state["deal_id"], "price": state.get("indicative_price")}
        ),
        extra={
            "deal_id": state["deal_id"],
            "query_category": state["query_category"],
            "asset_class": state.get("asset_class", "credit"),
            "indicative_price_hash": hash_inputs({"price": state.get("indicative_price")}),
        },
    )
    emit_compliance_event(event, _config)
    state["compliance_emitted"] = True
    return state


@traced_pipeline("pricing_pipeline", attribute_keys=["deal_id", "query_category"])
@log_calls()
@track_latency("gernas.pricing.pipeline_latency_ms", unit="ms", attribute_keys=["query_category"])
@count_calls("gernas.pricing.pipeline_runs_total", attribute_keys=["query_category"])
async def run_pricing_pipeline(deal_id: str, query_category: str, config) -> dict:
    """Execute the full pricing pipeline — simulates a LangGraph graph run."""
    init_agent(config)
    run_id = get_current_trace_id()
    state: dict = {
        "deal_id": deal_id,
        "query_category": query_category,
        "run_id": run_id,
        "asset_class": "credit",
    }

    # Emit compliance start event — bookends the completed event for audit trail
    if config.enable_compliance:
        start_event = ComplianceEvent(
            event_type="pricing_query_started",
            run_id=run_id,
            actor="pricing_agent",
            outcome="in_progress",
            payload_hash=hash_inputs({"deal_id": deal_id, "query_category": query_category}),
            extra={"deal_id": deal_id, "query_category": query_category},
        )
        emit_compliance_event(start_event, config)

    state = await validate_query(state)
    state = await fetch_deal_data(state)
    state = await compute_pricing(state)
    state = await emit_compliance_record(state)
    return state
