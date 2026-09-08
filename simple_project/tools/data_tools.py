"""Data tools — existing tool functions with beacon_kit decorators added.

The only change vs. a plain project is the @traced_tool import and decorator.
Business logic inside each function is untouched.
"""
from __future__ import annotations

import asyncio
import random

from beacon_kit import traced_tool, count_calls
from beacon_kit.circuit_breaker import TelemetryCircuitBreaker

# Circuit breakers: one per external dependency, each with its own fault tolerance budget.
# rwa_engine: strict (fail_max=3) — high-value risk data, fail fast
# deal_db:    moderate (fail_max=5) — DB retries tolerated briefly
# market_data: moderate (fail_max=5) — market feed momentary blips acceptable
rwa_breaker    = TelemetryCircuitBreaker(name="rwa_engine",  fail_max=3, reset_timeout=10)
db_breaker     = TelemetryCircuitBreaker(name="deal_db",     fail_max=5, reset_timeout=15)
market_breaker = TelemetryCircuitBreaker(name="market_data", fail_max=5, reset_timeout=15)


@traced_tool("rwa_engine_lookup")
@count_calls("gernas.tool.calls_total", attributes={"tool": "rwa_engine_lookup"})
@rwa_breaker
async def rwa_engine_lookup(deal_id: str) -> dict:
    """Look up risk-weighted assets for a deal. Simulates an HTTP call."""
    await asyncio.sleep(0.05)  # simulate latency
    if random.random() < 0.1:  # 10% simulated failure rate for demo
        raise ConnectionError(f"RWA engine timeout for deal {deal_id}")
    return {
        "deal_id": deal_id,
        "rwa_usd": round(random.uniform(1_000_000, 50_000_000), 2),
        "schema_version": "v2",
    }


@traced_tool("deal_db_lookup")
@count_calls("gernas.tool.calls_total", attributes={"tool": "deal_db_lookup"})
@db_breaker
async def deal_db_lookup(deal_id: str) -> dict:
    """Fetch deal metadata from the Deal DB."""
    await asyncio.sleep(0.02)
    return {
        "deal_id": deal_id,
        "counterparty": "[COUNTERPARTY_ID_PSEUDONYMOUS]",
        "currency": "USD",
        "notional": round(random.uniform(500_000, 10_000_000), 2),
        "schema_version": "v1",
    }


@traced_tool("market_data_fetch")
@count_calls("gernas.tool.calls_total", attributes={"tool": "market_data_fetch"})
@market_breaker
async def market_data_fetch(asset_class: str) -> dict:
    """Fetch current market rates for a given asset class."""
    await asyncio.sleep(0.03)
    return {
        "asset_class": asset_class,
        "rate": round(random.uniform(0.03, 0.08), 4),
        "source": "bloomberg_feed",
        "schema_version": "v1",
    }
