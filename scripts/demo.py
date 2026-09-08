"""GERNAS simple_project — 3-Layer Observability Demo

Run while the app is running in a separate terminal:
    uvicorn simple_project.main:app --reload   # Terminal 1 (server)
    python scripts\\demo.py                    # Terminal 2 (this script)

Sections
--------
1  System Check          GET /health
2  Pricing Query         POST /query
3  Layer 02 — Traces     Span waterfall tree (pipeline root + all nodes)
4  Layer 02 — Logs       Structured OTEL log records with trace_id correlation
5  Layer 02 — Metrics    Histograms (with dimensions), counters, circuit breaker gauges × 3
6  Layer 03 — Compliance Start + completed events, chain integrity verification
7  Cross-layer           trace_id linking all 3 layers
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx is required: python -m pip install httpx")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.text import Text
    from rich import box
except ImportError:
    print("rich is required: python -m pip install rich")
    sys.exit(1)

BASE_URL = "http://localhost:8000"
COMPLIANCE_FILE = Path(__file__).parent.parent / "compliance_events.jsonl"
console = Console()

# ── helpers ───────────────────────────────────────────────────────────────────

def _rule(title: str, style: str = "cyan") -> None:
    console.rule(f"[bold {style}]{title}[/bold {style}]")
    console.print()


def _kv_panel(title: str, rows: list[tuple[str, str]], border: str = "cyan") -> None:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="dim", no_wrap=True)
    t.add_column(style="white")
    for k, v in rows:
        t.add_row(k, v)
    console.print(Panel(t, title=f"[bold]{title}[/bold]", border_style=border, expand=False))


def _json_panel(title: str, data: dict, border: str = "cyan") -> None:
    console.print(Panel(
        Syntax(json.dumps(data, indent=2), "json", theme="monokai", word_wrap=True),
        title=f"[bold]{title}[/bold]", border_style=border, expand=False,
    ))


def _fetch(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        return httpx.request(method, f"{BASE_URL}{path}", timeout=15, **kwargs)
    except httpx.ConnectError:
        console.print(Panel(
            "[red]Could not connect to http://localhost:8000\n"
            "Start the server first:\n"
            "  uvicorn simple_project.main:app --reload[/red]",
            border_style="red",
        ))
        sys.exit(1)


# ── section 1: health check ───────────────────────────────────────────────────

def health_check() -> None:
    _rule("Step 1 — System Check  (GET /health)")

    resp = _fetch("GET", "/health")
    color = "green" if resp.status_code == 200 else "red"
    _kv_panel(
        "GET /health",
        [
            ("status", f"[{color}]HTTP {resp.status_code}[/{color}]"),
            ("body", json.dumps(resp.json())),
        ],
        border=color,
    )
    console.print()


# ── section 2: pricing query ──────────────────────────────────────────────────

def pricing_query() -> dict:
    _rule("Step 2 — Pricing Query  (POST /query)")

    payload = {"deal_id": "DEAL-42", "query_category": "standard_pricing"}
    headers = {"Content-Type": "application/json", "X-Run-ID": "demo-run-001"}

    _json_panel("Request body", payload, border="blue")
    console.print()

    resp = _fetch("POST", "/query", json=payload, headers=headers)
    data = resp.json()
    color = "green" if resp.status_code == 200 else "red"

    if resp.status_code == 200:
        _kv_panel(
            f"Response  HTTP {resp.status_code}",
            [
                ("deal_id", data.get("deal_id", "")),
                ("indicative_price", f"[bold white]{data.get('indicative_price', 'N/A')}[/bold white]"),
                ("run_id (trace_id)", f"[cyan]{data.get('run_id', '')}[/cyan]"),
                ("compliance_emitted", "[green]true[/green]" if data.get("compliance_emitted") else "[red]false[/red]"),
            ],
            border=color,
        )
    else:
        _json_panel(f"Response  HTTP {resp.status_code}", data, border="red")

    console.print()
    return data


# ── section 3: layer 02 — traces ──────────────────────────────────────────────

def show_traces(run_id: str) -> None:
    _rule("Step 3 — Layer 02: Agentic Runtime — Span Trace", style="bright_blue")

    console.print("[dim]Waiting for span buffer to populate…[/dim]")
    data = None
    for _ in range(10):
        time.sleep(0.5)
        resp = _fetch("GET", "/telemetry/recent")
        body = resp.json()
        if body.get("traces"):
            data = body
            break

    if not data or not data.get("traces"):
        console.print(Panel(
            "[yellow]No traces in buffer yet.\n"
            "Make sure EXPORTER_TYPE=pretty in .env and the server was restarted.[/yellow]",
            border_style="yellow",
        ))
        console.print()
        return

    trace = data["traces"][-1]
    tid = trace["trace_id"]
    spans = trace["spans"]

    by_sid = {s["span_id"]: s for s in spans}
    children: dict[str | None, list[dict]] = defaultdict(list)
    root = None
    for s in spans:
        pid = s.get("parent_id")
        if pid is None or pid not in by_sid:
            root = s
            children[None].append(s)
        else:
            children[pid].append(s)

    t = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold bright_blue",
        title=f"[bold]Span Waterfall — {trace.get('service', '')}[/bold]  [dim]trace: {tid[:16]}…[/dim]",
        title_justify="left",
        padding=(0, 1),
    )
    t.add_column("Span", no_wrap=True, min_width=32)
    t.add_column("Kind", style="dim", width=10)
    t.add_column("Duration", justify="right", width=10)
    t.add_column("Status", width=7)
    t.add_column("Key Attributes")

    def _dur(ms: float) -> str:
        c = "green" if ms < 100 else ("yellow" if ms < 500 else "red")
        return f"[{c}]{ms:.0f} ms[/{c}]"

    def _status(s: dict) -> str:
        return "[green]OK[/green]" if s["status"] == "OK" else "[bold red]ERROR[/bold red]"

    def _attr(s: dict) -> str:
        a = s.get("attrs", {})
        parts = []
        kind = s["kind"]
        if kind == "SERVER":
            if "service.run_id" in a:
                parts.append(f"run_id=[cyan]{str(a['service.run_id'])[:16]}[/cyan]")
        elif kind == "CLIENT":
            if "tool.latency_ms" in a:
                parts.append(f"latency=[yellow]{float(a['tool.latency_ms']):.0f}ms[/yellow]")
            has_err = str(a.get("tool.output.has_error", "False"))
            col = "red" if has_err == "True" else "green"
            parts.append(f"err=[{col}]{has_err}[/{col}]")
        elif kind == "INTERNAL":
            if "pricing.indicative_price" in a:
                parts.append(f"price=[bold white]{float(a['pricing.indicative_price']):.4f}[/bold white]")
            if "pricing.rwa_usd" in a:
                parts.append(f"rwa={int(a['pricing.rwa_usd']):,}")
            if "pipeline.deal_id" in a:
                parts.append(f"deal_id=[dim]{a['pipeline.deal_id']}[/dim]")
            if "pipeline.query_category" in a:
                parts.append(f"category=[dim]{a['pipeline.query_category']}[/dim]")
            if "node.deal_id" in a:
                parts.append(f"deal_id=[dim]{a['node.deal_id']}[/dim]")
            if "node.query_category" in a:
                parts.append(f"cat=[dim]{a['node.query_category']}[/dim]")
        return "  ".join(parts)

    def walk_tree(span: dict, prefix: str, is_last: bool) -> None:
        sid = span["span_id"]
        connector = "└ " if is_last else "├ "
        label = (prefix + connector if (prefix or span.get("parent_id")) else "") + span["name"]
        t.add_row(label, span["kind"], _dur(span["duration_ms"]), _status(span), _attr(span))
        child_list = children.get(sid, [])
        child_prefix = prefix + ("  " if is_last else "│ ")
        for i, child in enumerate(child_list):
            walk_tree(child, child_prefix, i == len(child_list) - 1)

    if root:
        walk_tree(root, "", True)

    console.print(t)
    console.print()


# ── section 4: layer 02 — logs ────────────────────────────────────────────────

def show_logs() -> None:
    _rule("Step 4 — Layer 02: Agentic Runtime — Structured Logs", style="green")

    console.print("[dim]Fetching OTEL log records from buffer…[/dim]")
    time.sleep(0.5)
    resp = _fetch("GET", "/telemetry/recent")
    logs = resp.json().get("logs", [])

    if not logs:
        console.print(Panel(
            "[yellow]No log records in buffer.\n"
            "Make sure EXPORTER_TYPE=pretty and the server was restarted.\n"
            "Logs appear only when @log_calls or logging.getLogger() is used.[/yellow]",
            border_style="yellow",
        ))
        console.print()
        return

    t = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold green",
        title="[bold]OTEL Structured Log Records[/bold]  [dim](trace_id linked)[/dim]",
        title_justify="left",
        padding=(0, 1),
    )
    t.add_column("Time", style="dim", width=12, no_wrap=True)
    t.add_column("Level", width=7)
    t.add_column("Logger", style="dim", no_wrap=True, max_width=28)
    t.add_column("Message")
    t.add_column("trace_id", style="dim", width=18, no_wrap=True)

    _level_color = {"ERROR": "bold red", "WARNING": "yellow", "WARN": "yellow", "DEBUG": "dim"}
    for r in logs[-20:]:  # show last 20
        color = _level_color.get(r.get("severity", "INFO"), "green")
        tid = r.get("trace_id", "")
        t.add_row(
            r.get("ts", ""),
            f"[{color}]{r.get('severity', 'INFO')}[/{color}]",
            r.get("logger", ""),
            r.get("body", ""),
            (tid[:16] + "…") if len(tid) > 16 else tid,
        )

    console.print(t)
    console.print(Panel(
        "[dim]Each log record carries the active [bold]trace_id[/bold] and [bold]span_id[/bold] "
        "injected by OTEL LoggingHandler.\n"
        "This links log lines directly to the span tree above — no separate log correlation needed.[/dim]",
        border_style="green",
        expand=False,
    ))
    console.print()


# ── section 5: layer 02 — metrics ─────────────────────────────────────────────

def show_metrics() -> None:
    _rule("Step 5 — Layer 02: Agentic Runtime — Metrics", style="magenta")

    console.print("[dim]Waiting for metric flush (up to 8 s)…[/dim]")
    metrics = []
    for _ in range(16):
        time.sleep(0.5)
        resp = _fetch("GET", "/telemetry/recent")
        metrics = resp.json().get("metrics", [])
        if metrics:
            break

    if not metrics:
        console.print(Panel(
            "[yellow]No metrics yet — flush interval is 5 s.\n"
            "Try running the demo again after sending a few more requests.[/yellow]",
            border_style="yellow",
        ))
        console.print()
        return

    t = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold magenta",
        title="[bold]Metric Snapshot[/bold]  [dim](GERNAS SDK — dimensional)[/dim]",
        title_justify="left",
        padding=(0, 1),
    )
    t.add_column("Metric", no_wrap=True, min_width=38)
    t.add_column("Type", style="dim", width=12)
    t.add_column("Value")
    t.add_column("Unit", style="dim", width=5)

    for m in metrics:
        t.add_row(m["name"], m["type"], m["value_str"], m.get("unit", ""))

    console.print(t)

    # Layer 01: show all 3 circuit breaker gauges
    cb_metrics = [m for m in metrics if "circuit_breaker" in m["name"]]
    if cb_metrics:
        rows = []
        for cb in cb_metrics:
            val = cb.get("value", 0)
            state_info = {0: ("CLOSED", "green"), 1: ("HALF-OPEN", "yellow"), 2: ("OPEN", "red")}.get(
                int(val), (str(val), "white")
            )
            cb_name = cb.get("attrs", {}).get("circuit_breaker.name", "")
            rows.append((
                f"circuit_breaker.state [{cb_name}]",
                f"[{state_info[1]}]{val} — {state_info[0]}[/{state_info[1]}]",
            ))
        rows.append(("", "[dim]0=CLOSED · 1=HALF-OPEN · 2=OPEN[/dim]"))
        _kv_panel("Layer 01 — Infrastructure Circuit Breakers", rows, border="cyan")
    console.print()


# ── section 6: layer 03 — compliance ─────────────────────────────────────────

def _verify_chain_local(events: list[dict]) -> tuple[bool, int]:
    """Re-implement verify_chain locally (hashlib only — no beacon_kit import)."""
    prev_hash = "0" * 64
    for i, ev in enumerate(events):
        signable = {k: v for k, v in ev.items() if k not in ("chain_hash", "signature")}
        canonical = json.dumps(signable, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256((prev_hash + canonical).encode()).hexdigest()
        if ev.get("chain_hash") != expected:
            return False, i
        prev_hash = expected
    return True, len(events)


def show_compliance(run_id: str) -> None:
    _rule("Step 6 — Layer 03: Compliance", style="yellow")

    if not COMPLIANCE_FILE.exists():
        console.print(Panel("[dim]compliance_events.jsonl not found[/dim]", border_style="dim"))
        console.print()
        return

    lines = [l.strip() for l in COMPLIANCE_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        console.print(Panel("[dim]No compliance events recorded yet[/dim]", border_style="dim"))
        console.print()
        return

    all_events = [json.loads(l) for l in lines]
    chain_ok, chain_len = _verify_chain_local(all_events)
    chain_str = (
        f"[green]✓ verified ({chain_len} events)[/green]"
        if chain_ok
        else f"[red]✗ broken at event {chain_len}[/red]"
    )

    # Show start + completed events for this run
    run_events = [e for e in all_events if e.get("run_id") == run_id or e.get("trace_id") == run_id]
    if not run_events:
        run_events = all_events[-2:]  # fallback: last 2

    for ev in run_events:
        event_type = ev.get("event_type", "")
        color = "yellow" if "started" in event_type else "green"
        label = "Compliance Event — START" if "started" in event_type else "Compliance Event — COMPLETED"
        _kv_panel(
            label,
            [
                ("event_type",   f"[bold white]{event_type}[/bold white]"),
                ("run_id",       f"[cyan]{ev.get('run_id', '')}[/cyan]"),
                ("actor",        ev.get("actor", "")),
                ("outcome",      f"[{color}]{ev.get('outcome', '')}[/{color}]"),
                ("payload_hash", f"[dim]{ev.get('payload_hash', '')[:32]}…[/dim]  [italic dim](SHA-256)[/italic dim]"),
                ("chain_hash",   f"[dim]{ev.get('chain_hash', '')[:32]}…[/dim]"),
                ("signature",    f"[dim]{ev.get('signature', '')[:32]}…[/dim]  [italic dim](HMAC-SHA256)[/italic dim]"),
                ("trace_id",     f"[cyan]{ev.get('trace_id', '')}[/cyan]"),
                ("timestamp",    ev.get("timestamp", "")),
            ],
            border=color,
        )

    # Chain integrity summary
    console.print(Panel(
        f"Chain integrity: {chain_str}\n"
        "[dim]SHA-256(previous_hash + canonical_json) — tamper-evident, sequentially linked[/dim]",
        title="[bold]Audit Trail Integrity[/bold]",
        border_style="yellow",
        expand=False,
    ))
    console.print()


# ── section 7: cross-layer correlation ────────────────────────────────────────

def cross_layer_summary(run_id: str) -> None:
    _rule("Step 7 — Cross-Layer Correlation", style="white")

    console.print(Panel(
        f"[bold cyan]trace_id = {run_id}[/bold cyan]\n\n"
        "  [bright_blue]Layer 02 Traces[/bright_blue]   → [dim]pricing_pipeline[/dim] root span carries this as W3C TraceContext trace ID\n"
        "  [green]Layer 02 Logs[/green]     → every log record from [dim]@log_calls[/dim] includes this trace_id via LoggingHandler\n"
        "  [magenta]Layer 02 Metrics[/magenta]  → [dim]query_category[/dim] Baggage tag flows into histogram + counter dimensions\n"
        "  [yellow]Layer 03 Compliance[/yellow] → [dim]ComplianceEvent.run_id[/dim] and [dim].trace_id[/dim] equal this value\n\n"
        "[dim]One ID links infrastructure health, agent reasoning, structured logs, and the regulatory audit trail.[/dim]",
        title="[bold]The Single Cross-Layer Correlation Key[/bold]",
        border_style="white",
        expand=False,
    ))
    console.print()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    console.print()
    console.print(Panel(
        "[bold white]GERNAS simple_project[/bold white]  ·  beacon_kit v0.2.0 — Full 3-Layer Observability\n\n"
        "  [bright_blue]Layer 02[/bright_blue]  Agentic Runtime — traces (pipeline root span + nodes) · metrics (with dimensions) · logs\n"
        "  [yellow]Layer 03[/yellow]  Compliance — start + completed events · tamper-proof signed audit trail\n"
        "  [white]Layer 01[/white]  Infrastructure — circuit breaker gauge × 3 tools · HTTP metrics\n\n"
        "[dim]The server terminal shows span waterfalls, metric snapshots, and log records as they happen.[/dim]",
        border_style="cyan",
        expand=False,
    ))
    console.print()

    health_check()
    time.sleep(0.2)

    response_data = pricing_query()
    run_id = response_data.get("run_id", "")

    show_traces(run_id)
    show_logs()
    show_metrics()
    show_compliance(run_id)
    cross_layer_summary(run_id)


if __name__ == "__main__":
    main()
