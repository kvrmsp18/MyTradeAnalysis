#!/usr/bin/env python3
"""Deterministic, fail-closed evaluation of the frozen strategy rules."""
from __future__ import annotations
import math
from typing import Any

WINDOW = 125

def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None

def _rsi(closes: list[float], period: int = 14) -> float | None:
    values = [_num(value) for value in closes]
    if len(values) < period + 1 or any(value is None for value in values[-(period + 1):]):
        return None
    tail = [float(value) for value in values[-(period + 1):] if value is not None]
    changes = [b - a for a, b in zip(tail, tail[1:])]
    gains = sum(max(change, 0.0) for change in changes) / period
    losses = sum(max(-change, 0.0) for change in changes) / period
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    return 100.0 - (100.0 / (1.0 + gains / losses))

def evaluate_daily_strategies(daily_candles: list[dict[str, Any]], current_price: Any,
                              current_volume: Any, *, current_rsi: Any = None) -> dict[str, dict[str, Any]]:
    """Caller must pass only the 125 previous completed daily candles."""
    price, volume = _num(current_price), _num(current_volume)
    rows = daily_candles[-WINDOW:]
    highs = [_num(row.get("high")) for row in rows]
    lows = [_num(row.get("low")) for row in rows]
    volumes = [_num(row.get("volume")) for row in rows]
    closes = [_num(row.get("close")) for row in rows]
    history_ok = len(rows) == WINDOW and all(v is not None for v in highs + lows + volumes + closes)
    avg_volume = sum(float(v) for v in volumes) / WINDOW if history_ok else None
    highest_high = max(float(v) for v in highs) if history_ok else None
    lowest_low = min(float(v) for v in lows) if history_ok else None
    rsi_value = _num(current_rsi)
    if rsi_value is None and history_ok and price is not None:
        rsi_value = _rsi([float(v) for v in closes if v is not None] + [price])
    unavailable = not history_ok or price is None or volume is None or avg_volume is None or rsi_value is None
    if unavailable:
        reason = "INSUFFICIENT_DAILY_HISTORY_OR_CURRENT_PRICE_VOLUME_RSI"
        breakout = {"status": "UNAVAILABLE", "eligible": False, "direction": "LONG", "reason": reason}
        breakdown = {"status": "UNAVAILABLE", "eligible": False, "direction": "BEARISH_WARNING_ONLY", "reason": reason}
    else:
        breakout_checks = {
            "price_above_previous_125d_high": price > float(highest_high),
            "volume_above_2x_previous_125d_average": volume > 2.0 * float(avg_volume),
            "daily_rsi14_below_70": rsi_value < 70.0,
        }
        breakdown_checks = {
            "price_below_previous_125d_low": price < float(lowest_low),
            "volume_above_previous_125d_average": volume > float(avg_volume),
            "daily_rsi14_above_30": rsi_value > 30.0,
        }
        breakout_pass, breakdown_pass = all(breakout_checks.values()), all(breakdown_checks.values())
        metrics = {"current_price": price, "current_volume": volume,
                   "previous_125d_average_volume": avg_volume, "daily_rsi14": round(rsi_value, 4)}
        breakout = {"status": "SIGNAL" if breakout_pass else "NO_SIGNAL", "eligible": breakout_pass,
                    "direction": "LONG", "checks": breakout_checks,
                    "metrics": {**metrics, "previous_125d_high": highest_high}}
        breakdown = {"status": "BEARISH_WARNING" if breakdown_pass else "NO_SIGNAL", "eligible": False,
                     "direction": "BEARISH_WARNING_ONLY", "checks": breakdown_checks,
                     "metrics": {**metrics, "previous_125d_low": lowest_low},
                     "reason": "This signal never authorizes short or options orders."}
    return {"breakout_125d": breakout, "richie_rich_breakdown_125d": breakdown}

def evaluate_hourly_rsi(hourly_candles: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Evaluate hourly RSI only when real hourly candle data is supplied."""
    candles = hourly_candles or []
    closes = [_num(row.get("close")) for row in candles]
    if len(closes) < 15 or any(value is None for value in closes[-15:]):
        return {"status": "UNAVAILABLE", "entry_signal": False, "target_signal": False,
                "stop_signal": False, "reason": "15 valid hourly closes are required."}
    value = _rsi([float(v) for v in closes if v is not None])
    if value is None:
        return {"status": "UNAVAILABLE", "entry_signal": False, "target_signal": False,
                "stop_signal": False, "reason": "Hourly RSI could not be calculated."}
    return {"status": "READY", "rsi14": round(value, 4),
            "entry_signal": 58.0 < value < 65.0, "target_signal": value > 75.0,
            "stop_signal": value < 40.0,
            "note": "RSI signals are not guaranteed fills; retain independent protective stops."}

def evaluate_strategy_signals(candles: list[dict[str, Any]], interval: str,
                              quote: dict[str, Any]) -> dict[str, Any]:
    if interval != "1d":
        daily = {key: {"status": "UNAVAILABLE", "eligible": False,
                       "reason": "Daily strategy requires validated daily candles; received " + str(interval)}
                 for key in ("breakout_125d", "richie_rich_breakdown_125d")}
    else:
        daily = evaluate_daily_strategies(candles, quote.get("price"), quote.get("volume"))
    hourly = evaluate_hourly_rsi(None)  # hourly history is not yet fetched by SCRAP
    return {"version": "strategy-reference-v1", "daily": daily, "hourly_rsi_momentum": hourly,
            "execution_authorized": False,
            "note": "Strategy signals are recorded for review and do not authorize orders."}
