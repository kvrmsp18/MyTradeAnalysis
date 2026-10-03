#!/usr/bin/env python3
"""Live execution engine.

Consumes the same decision-time ledger as paper execution, but submits real
NSE_EQ intraday orders through scripts/dhan_order.py only when the explicit
server-side live gates are enabled.

No browser code can place an order. The engine re-checks every safety gate
before each order and records broker order ids for reconciliation.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dhan_order import LiveOrderBlocked, is_fill_status, order_detail, positions, submit_order

LEDGER_ROOT = Path("data/ledger")
STATE = Path("data/live/state.json")
EVENTS = Path("data/live/events")
PUBLIC_STATE = Path("public/data/live_state.json")
SNAPSHOT = Path("public/data/market_snapshot.json")
MAX_POSITIONS = int(os.getenv("LIVE_MAX_POSITIONS", "2"))
MAX_POSITION_PCT = float(os.getenv("LIVE_MAX_POSITION_PCT", "20"))
TARGET_PCT = float(os.getenv("LIVE_TARGET_PCT", "2.0"))
STOP_PCT = float(os.getenv("LIVE_STOP_PCT", "1.0"))
MAX_DAILY_LOSS = float(os.getenv("LIVE_MAX_DAILY_LOSS", "500"))
STALE_MINUTES = float(os.getenv("LIVE_MAX_DATA_AGE_MINUTES", "5"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read(path: Path, default: dict, strict: bool = False) -> dict:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    except Exception:
        if strict:
            raise RuntimeError(f"Invalid live state: {path}")
        return default


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="._live_", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def fresh(snapshot: dict) -> bool:
    raw = snapshot.get("data_as_of")
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - stamp).total_seconds() / 60
        return 0 <= age <= STALE_MINUTES
    except (TypeError, ValueError):
        return False


def latest_ledger() -> Path | None:
    files = sorted(LEDGER_ROOT.glob("*/[0-9]*.json"))
    return files[-1] if files else None


def market_clock() -> tuple[datetime, int]:
    ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    return ist, ist.hour * 60 + ist.minute


def publish(state: dict, status: str, reason: str = "") -> None:
    payload = {
        "schema_version": "1.0",
        "mode": "LIVE",
        "status": status,
        "reason": reason,
        "cash": state.get("cash"),
        "positions": state.get("positions", {}),
        "realized_pnl": state.get("realized_pnl", 0),
        "daily_pnl": state.get("daily_pnl", 0),
        "trade_count": len(state.get("trades", [])),
        "live_orders_enabled": os.getenv("LIVE_TRADING_ENABLED") == "1",
        "generated_at": now(),
    }
    save(PUBLIC_STATE, payload)


def fail_closed(reason: str) -> int:
    state = read(STATE, {"positions": {}, "trades": [], "daily_pnl": 0})
    publish(state, "BLOCKED", reason)
    print("LIVE_EXECUTION_BLOCKED=" + reason)
    return 0


def main() -> int:
    try:
        from dhan_order import config_from_env
        config_from_env()
    except LiveOrderBlocked as exc:
        return fail_closed(str(exc))

    if os.getenv("TRADING_MODE", "PAPER").upper() != "LIVE":
        return fail_closed("TRADING_MODE is not LIVE")

    if os.getenv("LIVE_KILL_SWITCH", "0") == "1":
        return fail_closed("LIVE_KILL_SWITCH=1")

    ledger_path = latest_ledger()
    snapshot = read(SNAPSHOT, {})
    if not ledger_path:
        return fail_closed("NO_DECISION_LEDGER")
    if not fresh(snapshot):
        return fail_closed("STALE_MARKET_DATA")
    if snapshot.get("status") != "LIVE_MARKET_DATA":
        return fail_closed("PRIMARY_DHAN_MARKET_DATA_REQUIRED")
    if read(ledger_path, {}).get("mode") != "PAPER":
        return fail_closed("DECISION_LEDGER_MODE_INVALID")

    ist, minutes = market_clock()
    if ist.weekday() >= 5 or not (9 * 60 + 15 <= minutes < 15 * 60 + 25):
        return fail_closed("OUTSIDE_ENTRY_WINDOW")

    state = read(STATE, {"positions": {}, "trades": [], "daily_pnl": 0.0, "last_processed_ledger": None}, strict=True)
    if state.get("last_processed_ledger") == str(ledger_path):
        publish(state, "IDLE", "LEDGER_ALREADY_PROCESSED")
        return 0

    if float(state.get("daily_pnl", 0) or 0) <= -MAX_DAILY_LOSS:
        return fail_closed("DAILY_LOSS_LIMIT")

    candidates = [x for x in read(ledger_path, {}).get("candidates", []) if x.get("decision") == "REVIEW"]
    candidates.sort(key=lambda x: x.get("ranking", 999999))
    snapshot_by_symbol = {str(x.get("symbol")): x for x in snapshot.get("stocks", [])}

    # Reconcile broker positions before opening anything.
    broker_positions = positions()
    broker_by_symbol = {}
    for row in broker_positions:
        symbol = str(row.get("tradingSymbol") or row.get("trading_symbol") or row.get("symbol") or "")
        if symbol:
            broker_by_symbol[symbol] = row
    state["broker_positions_snapshot"] = broker_positions

    events = []
    open_count = len([p for p in broker_positions if float(p.get("netQty", p.get("net_qty", 0)) or 0) != 0])

    for candidate in candidates:
        if open_count >= MAX_POSITIONS:
            break
        symbol = str(candidate.get("symbol") or "")
        quote = snapshot_by_symbol.get(symbol, {})
        security_id = quote.get("security_id")
        price = float(quote.get("price") or 0)
        if not security_id or price <= 0:
            continue
        if symbol in broker_by_symbol and float(broker_by_symbol[symbol].get("netQty", broker_by_symbol[symbol].get("net_qty", 0)) or 0) != 0:
            continue

        score = float(candidate.get("features", {}).get("score") or 0)
        scrap_score = float(candidate.get("scrap_result", {}).get("score") or 0)
        if score < 65 or scrap_score < 60:
            continue

        # Live capital is checked against Dhan's current broker funds, not the
        # paper balance. The workflow supplies LIVE_AVAILABLE_CAPITAL.
        available = float(os.getenv("LIVE_AVAILABLE_CAPITAL", "0") or 0)
        if available <= 0:
            return fail_closed("LIVE_FUNDS_UNAVAILABLE")
        position_cap = available * MAX_POSITION_PCT / 100
        quantity = int(position_cap // price)
        if quantity < 1:
            continue

        tag = ("MTA_" + datetime.now(timezone.utc).strftime("%H%M%S") + "_" + symbol)[:30]
        response = submit_order(
            transaction_type="BUY",
            exchange_segment="NSE_EQ",
            security_id=str(security_id),
            quantity=quantity,
            product_type="INTRADAY",
            order_type="MARKET",
            tag=tag,
        )
        order_id = str(response.get("orderId") or response.get("order_id") or response.get("data", {}).get("orderId") or "")
        if not order_id:
            raise RuntimeError("Dhan accepted request without returning an order id")

        detail = order_detail(order_id)
        status_value = detail.get("orderStatus") or detail.get("order_status") or detail.get("status")
        event = {
            "side": "BUY",
            "symbol": symbol,
            "quantity": quantity,
            "security_id": str(security_id),
            "requested_price": price,
            "order_id": order_id,
            "broker_status": status_value,
            "submitted_at": now(),
            "filled": is_fill_status(status_value),
            "target_pct": TARGET_PCT,
            "stop_pct": STOP_PCT,
            "paper_order": False,
        }
        events.append(event)
        state.setdefault("trades", []).append(event)
        open_count += 1

    state["last_processed_ledger"] = str(ledger_path)
    state["last_run_at"] = now()
    state["last_events"] = events
    save(STATE, state)
    for idx, event in enumerate(events, 1):
        save(EVENTS / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{idx}_{event['side']}_{event['symbol']}.json", event)
    publish(state, "ORDERS_SUBMITTED" if events else "NO_TRADE", "LIVE_ENGINE_COMPLETE")
    print(f"LIVE_EXECUTION_COMPLETE events={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
