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


def _num(row: dict, *keys: str) -> float:
    for key in keys:
        try:
            value = row.get(key)
            if value is not None and value != "":
                return float(value)
        except (TypeError, ValueError):
            pass
    return 0.0


def _symbol(row: dict) -> str:
    return str(row.get("tradingSymbol") or row.get("trading_symbol") or row.get("symbol") or "")


def _net_qty(row: dict) -> int:
    return int(_num(row, "netQty", "net_qty", "quantity"))


def _market_price(row: dict) -> float:
    return _num(row, "lastTradedPrice", "last_traded_price", "ltp", "marketPrice", "market_price")


def _average_buy(row: dict) -> float:
    return _num(row, "buyAvg", "buy_avg", "averagePrice", "average_price")


def _security_id(row: dict) -> str:
    return str(row.get("securityId") or row.get("security_id") or "")


def manage_positions(broker_positions: list[dict], state: dict, ist: datetime, fresh_data: bool) -> list[dict]:
    events = []
    minutes = ist.hour * 60 + ist.minute
    eod_exit = minutes >= 15 * 60 + 29
    for row in broker_positions:
        qty = _net_qty(row)
        if qty <= 0:
            continue
        symbol = _symbol(row)
        current = _market_price(row)
        entry = _average_buy(row)
        security_id = _security_id(row)
        if not symbol or current <= 0 or entry <= 0 or not security_id:
            continue
        return_pct = (current - entry) / entry * 100
        reason = "EOD_EXIT" if eod_exit else "TARGET" if fresh_data and return_pct >= TARGET_PCT else "STOP_LOSS" if fresh_data and return_pct <= -STOP_PCT else None
        if reason is None:
            continue
        response = submit_order(
            transaction_type="SELL",
            exchange_segment="NSE_EQ",
            security_id=security_id,
            quantity=qty,
            product_type="INTRADAY",
            order_type="MARKET",
            tag=("MTA_EXIT_" + symbol)[:30],
        )
        order_id = str(response.get("orderId") or response.get("order_id") or response.get("data", {}).get("orderId") or "")
        if not order_id:
            raise RuntimeError("Dhan accepted exit request without an order id")
        detail = order_detail(order_id)
        status_value = detail.get("orderStatus") or detail.get("order_status") or detail.get("status")
        pnl = (current - entry) * qty
        event = {
            "side": "SELL", "symbol": symbol, "quantity": qty, "security_id": security_id,
            "requested_price": current, "entry_price": entry, "estimated_pnl": round(pnl, 2),
            "return_pct": round(return_pct, 4), "reason": reason, "order_id": order_id,
            "broker_status": status_value, "submitted_at": now(), "filled": is_fill_status(status_value),
            "paper_order": False,
        }
        events.append(event)
        state.setdefault("trades", []).append(event)
        state["daily_pnl"] = round(float(state.get("daily_pnl", 0) or 0) + pnl, 2)
    return events


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

    ledger = read(ledger_path, {})
    if ledger.get("mode") != "PAPER":
        return fail_closed("DECISION_LEDGER_MODE_INVALID")

    ist, minutes = market_clock()
    if ist.weekday() >= 5:
        return fail_closed("WEEKEND")
    if not (9 * 60 + 15 <= minutes < 15 * 60 + 30):
        return fail_closed("OUTSIDE_MARKET_SESSION")

    state = read(STATE, {"positions": {}, "trades": [], "daily_pnl": 0.0, "last_processed_ledger": None}, strict=True)
    state.setdefault("trades", [])
    state.setdefault("daily_pnl", 0.0)

    if float(state.get("daily_pnl", 0) or 0) <= -MAX_DAILY_LOSS:
        return fail_closed("DAILY_LOSS_LIMIT")

    broker_positions = positions()
    state["broker_positions_snapshot"] = broker_positions
    events = manage_positions(broker_positions, state, ist, True)

    # Do not open new positions during the final five minutes; only manage exits.
    if minutes >= 15 * 60 + 25:
        state["last_processed_ledger"] = str(ledger_path)
        state["last_run_at"] = now()
        state["last_events"] = events
        save(STATE, state)
        publish(state, "EXIT_ONLY", "FINAL_MINUTES")
        return 0

    if state.get("last_processed_ledger") == str(ledger_path):
        publish(state, "IDLE", "LEDGER_ALREADY_PROCESSED")
        return 0

    candidates = [x for x in ledger.get("candidates", []) if x.get("decision") == "REVIEW"]
    candidates.sort(key=lambda x: x.get("ranking", 999999))
    snapshot_by_symbol = {str(x.get("symbol")): x for x in snapshot.get("stocks", [])}
    broker_by_symbol = {_symbol(x): x for x in broker_positions if _symbol(x)}

    available = float(os.getenv("LIVE_AVAILABLE_CAPITAL", "0") or 0)
    if available <= 0:
        return fail_closed("LIVE_FUNDS_UNAVAILABLE")
    position_cap = available * MAX_POSITION_PCT / 100
    open_count = len([p for p in broker_positions if _net_qty(p) != 0])

    for candidate in candidates:
        if open_count >= MAX_POSITIONS:
            break
        symbol = str(candidate.get("symbol") or "")
        quote = snapshot_by_symbol.get(symbol, {})
        security_id = quote.get("security_id")
        price = float(quote.get("price") or 0)
        if not security_id or price <= 0:
            continue
        if symbol in broker_by_symbol and _net_qty(broker_by_symbol[symbol]) != 0:
            continue

        score = float(candidate.get("features", {}).get("score") or 0)
        scrap_score = float(candidate.get("scrap_result", {}).get("score") or 0)
        ai_verdict = str(candidate.get("ai_council", {}).get("symbol_verdict") or candidate.get("ai_symbol_verdict") or "")
        if score < 65 or scrap_score < 60 or ai_verdict != "SUPPORT":
            continue

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
            "side": "BUY", "symbol": symbol, "quantity": quantity, "security_id": str(security_id),
            "requested_price": price, "order_id": order_id, "broker_status": status_value,
            "submitted_at": now(), "filled": is_fill_status(status_value), "target_pct": TARGET_PCT,
            "stop_pct": STOP_PCT, "paper_order": False,
        }
        events.append(event)
        state["trades"].append(event)
        open_count += 1

    state["last_processed_ledger"] = str(ledger_path)
    state["last_run_at"] = now()
    state["last_events"] = events
    save(STATE, state)
    for idx, event in enumerate(events, 1):
        save(EVENTS / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{idx}_{event['side']}_{event['symbol']}.json", event)
    publish(state, "ORDERS_SUBMITTED" if events else "NO_TRADE", "LIVE_ENGINE_COMPLETE")
    print(f"LIVE_EXECUTION_COMPLETE events={len(events)} daily_pnl={state.get('daily_pnl', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
