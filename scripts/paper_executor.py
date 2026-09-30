#!/usr/bin/env python3
"""Deterministic paper execution engine. Never sends broker orders.

Entry requirements:
- valid PAPER ledger
- real market snapshot (Dhan/NSE/Yahoo fallback)
- market open
- deterministic review candidate
- SCRAP threshold
- sufficient paper cash
- sufficient broker funds check when available

There is no share-price cap. A high-priced share is allowed when the
calculated quantity is affordable; otherwise it is skipped with an explicit
INSUFFICIENT_CAPITAL reason.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LEDGER_ROOT = Path("data/ledger")
STATE = Path("data/paper/state.json")
EVENTS = Path("data/paper/events")
PUBLIC_STATE = Path("public/data/paper_state.json")
SNAPSHOT = Path("public/data/market_snapshot.json")

CAPITAL = float(os.getenv("PAPER_STARTING_CAPITAL", os.getenv("PAPER_ANALYSIS_BUDGET", "1000")) or 1000)
ANALYSIS_BUDGET = max(1000.0, float(os.getenv("PAPER_ANALYSIS_BUDGET", "1000") or 1000))
MAX_POS_PCT = float(os.getenv("PAPER_MAX_POSITION_PCT", "20"))
TARGET_PCT = float(os.getenv("PAPER_TARGET_PCT", "2.0"))
STOP_PCT = float(os.getenv("PAPER_STOP_PCT", "1.0"))
MAX_POSITIONS = int(os.getenv("PAPER_MAX_POSITIONS", "2"))
FUNDS_STATUS = os.getenv("PAPER_FUNDS_STATUS", "UNAVAILABLE")
AVAILABLE_FUNDS = float(os.getenv("PAPER_AVAILABLE_CAPITAL", "0") or 0)


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except Exception:
        return default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def latest_ledger():
    files = sorted(LEDGER_ROOT.glob("*/[0-9]*.json"))
    return files[-1] if files else None


def price(candidate):
    try:
        value = float(candidate.get("quote", {}).get("price"))
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def publish_state(state):
    # This is paper-account state only; it contains no Dhan credentials or
    # broker-funds balance.
    public = {
        "schema_version": "1.1",
        "mode": "PAPER",
        "cash": round(float(state.get("cash", 0)), 2),
        "positions": state.get("positions", {}),
        "realized_pnl": round(float(state.get("realized_pnl", 0)), 2),
        "trade_count": len(state.get("trades", [])),
        "last_processed_ledger": state.get("last_processed_ledger"),
        "funds_check": "PASS" if FUNDS_STATUS == "READY" else "FALLBACK_MINIMUM",
        "analysis_budget": round(ANALYSIS_BUDGET, 2),
        "budget_rule": "Dhan available funds when available; otherwise ₹1,000 paper minimum",
        "live_orders_enabled": False,
        "generated_at": now(),
    }
    save(PUBLIC_STATE, public)


def main():
    ledger_path = latest_ledger()
    if not ledger_path:
        print("No ledger; no paper execution.")
        return 0

    ledger = read(ledger_path, {})
    snapshot = read(SNAPSHOT, {})

    if ledger.get("mode") != "PAPER":
        print("Non-paper ledger; no execution.")
        return 0

    if snapshot.get("status") not in (
        "LIVE_MARKET_DATA",
        "LIVE_MARKET_DATA_NSE",
        "LIVE_MARKET_DATA_NSE_PROXY",
        "LIVE_MARKET_DATA_FALLBACK",
    ):
        print("No validated market snapshot; no execution.")
        return 0

    state = read(
        STATE,
        {
            "schema_version": "1.0",
            "cash": CAPITAL,
            "positions": {},
            "realized_pnl": 0.0,
            "trades": [],
            "last_processed_ledger": None,
        },
    )
    state.setdefault("cash", CAPITAL)
    state.setdefault("positions", {})
    state.setdefault("realized_pnl", 0.0)
    state.setdefault("trades", [])

    if state.get("last_processed_ledger") == str(ledger_path):
        publish_state(state)
        print("Ledger already processed.")
        return 0

    events = []
    quote_map = {
        str(item.get("symbol")): item
        for item in snapshot.get("stocks", [])
        if item.get("symbol")
    }

    test_clock = os.getenv("PAPER_ENGINE_TEST_TIME_IST")
    if test_clock:
        ist = datetime.strptime(test_clock, "%Y-%m-%d %H:%M").replace(
            tzinfo=ZoneInfo("Asia/Kolkata")
        )
    else:
        ist = datetime.now(ZoneInfo("Asia/Kolkata"))

    market_minutes = ist.hour * 60 + ist.minute
    eod_exit = ist.weekday() < 5 and market_minutes >= 15 * 60 + 29
    entry_allowed = ist.weekday() < 5 and 9 * 60 + 15 <= market_minutes < 15 * 60 + 25

    # Manage existing positions first.
    for symbol, position in list(state["positions"].items()):
        quote = quote_map.get(symbol)
        current = price({"quote": quote}) if quote else None
        if current is None:
            continue

        entry = float(position["entry_price"])
        quantity = int(position["quantity"])
        return_pct = (current - entry) / entry * 100
        reason = (
            "EOD_EXIT"
            if eod_exit
            else "TARGET"
            if return_pct >= TARGET_PCT
            else "STOP_LOSS"
            if return_pct <= -STOP_PCT
            else None
        )

        if reason:
            proceeds = current * quantity
            pnl = (current - entry) * quantity
            state["cash"] = round(state["cash"] + proceeds, 2)
            state["realized_pnl"] = round(state["realized_pnl"] + pnl, 2)
            trade = {
                "side": "SELL",
                "symbol": symbol,
                "quantity": quantity,
                "price": current,
                "entry_price": entry,
                "pnl": round(pnl, 2),
                "reason": reason,
                "timestamp": now(),
            }
            state["trades"].append(trade)
            events.append(trade)
            del state["positions"][symbol]

    open_count = len(state["positions"])

    if not entry_allowed:
        candidates = []
    else:
        candidates = [
            candidate
            for candidate in ledger.get("candidates", [])
            if candidate.get("decision") == "REVIEW"
            and candidate.get("features", {}).get("score", 0) >= 65
        ]
        candidates.sort(key=lambda candidate: candidate.get("ranking", 9999))

    broker_available = AVAILABLE_FUNDS if FUNDS_STATUS == "READY" else ANALYSIS_BUDGET
    effective_buying_power = min(float(state["cash"]), broker_available, ANALYSIS_BUDGET)
    position_value_cap = effective_buying_power * MAX_POS_PCT / 100

    for candidate in candidates:
        if open_count >= MAX_POSITIONS:
            break

        symbol = str(candidate.get("symbol"))
        current = price(candidate)

        if not symbol or current is None or symbol in state["positions"] or current <= 0:
            continue

        try:
            scrap_score = float(candidate.get("scrap_result", {}).get("score"))
        except (TypeError, ValueError):
            continue

        if scrap_score < 60:
            continue

        quantity = int(position_value_cap // current)
        if quantity < 1:
            candidate.setdefault("execution", {})["reason"] = "INSUFFICIENT_CAPITAL"
            continue

        cost = quantity * current
        if cost > state["cash"] or cost > broker_available:
            candidate.setdefault("execution", {})["reason"] = "INSUFFICIENT_CAPITAL"
            continue

        state["cash"] = round(state["cash"] - cost, 2)
        state["positions"][symbol] = {
            "quantity": quantity,
            "entry_price": current,
            "entry_time": now(),
            "target_price": round(current * (1 + TARGET_PCT / 100), 4),
            "stop_price": round(current * (1 - STOP_PCT / 100), 4),
            "score": candidate.get("features", {}).get("score"),
        }

        trade = {
            "side": "BUY",
            "symbol": symbol,
            "quantity": quantity,
            "price": current,
            "cost": round(cost, 2),
            "score": candidate.get("features", {}).get("score"),
            "timestamp": now(),
            "funds_check": "PASS",
            "live_order_sent": False,
        }
        state["trades"].append(trade)
        events.append(trade)
        open_count += 1

    state["last_processed_ledger"] = str(ledger_path)
    save(STATE, state)

    for candidate in ledger.get("candidates", []):
        symbol = str(candidate.get("symbol"))
        matching = [event for event in events if event["symbol"] == symbol]
        execution = candidate.setdefault("execution", {})
        execution.update(
            {
                "mode": "PAPER",
                "order_submitted": bool(matching),
                "paper_events": matching,
                "live_order_sent": False,
                "funds_check": "PASS" if FUNDS_STATUS == "READY" else "FALLBACK_MINIMUM",
                "analysis_budget": round(ANALYSIS_BUDGET, 2),
                "reason": (
                    "PAPER_SIMULATED_FILL"
                    if matching
                    else execution.get("reason", "NO_PAPER_ORDER")
                ),
            }
        )

    ledger["paper_account"] = {
        "cash": state["cash"],
        "open_positions": state["positions"],
        "realized_pnl": state["realized_pnl"],
    }
    ledger["paper_events"] = events
    ledger.setdefault("safety", {})["live_orders_enabled"] = False
    ledger["safety"]["funds_check_required"] = True
    ledger["safety"]["stock_specific_learning_enabled"] = False
    save(ledger_path, ledger)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    for index, event in enumerate(events, 1):
        save(
            EVENTS / f"{stamp}_{index}_{event['side'].lower()}_{event['symbol']}.json",
            {
                "schema_version": "1.0",
                "paper_only": True,
                "live_trading_enabled": False,
                "event": event,
            },
        )

    publish_state(state)
    print(
        f"Paper execution complete: {len(events)} event(s), "
        f"cash={state['cash']}, realized_pnl={state['realized_pnl']}, "
        f"funds_check={FUNDS_STATUS}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
