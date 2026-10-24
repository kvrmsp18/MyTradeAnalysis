#!/usr/bin/env python3
"""Offline tests for strategy-reference-v1."""
from __future__ import annotations
import importlib.util
from pathlib import Path
PATH = Path(__file__).with_name("strategy_signals.py")
spec = importlib.util.spec_from_file_location("strategy_signals_test_module", PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

def candles(count=125, *, high=100.0, low=90.0, close=95.0, volume=1000.0):
    return [{"high": high, "low": low, "close": close, "volume": volume} for _ in range(count)]

def main():
    history = candles()
    breakout = module.evaluate_daily_strategies(history, 101, 2500, current_rsi=60)
    assert breakout["breakout_125d"]["status"] == "SIGNAL"
    assert breakout["richie_rich_breakdown_125d"]["status"] == "NO_SIGNAL"
    breakdown = module.evaluate_daily_strategies(
        candles(high=110, low=100, close=105, volume=1000), 99, 1500, current_rsi=40)
    assert breakdown["richie_rich_breakdown_125d"]["status"] == "BEARISH_WARNING"
    assert breakdown["richie_rich_breakdown_125d"]["eligible"] is False
    assert breakdown["richie_rich_breakdown_125d"]["direction"] == "BEARISH_WARNING_ONLY"
    assert module.evaluate_daily_strategies(history, 101, None, current_rsi=60)["breakout_125d"]["status"] == "UNAVAILABLE"
    assert module.evaluate_daily_strategies(candles(124), 101, 2500, current_rsi=60)["breakout_125d"]["status"] == "UNAVAILABLE"
    assert module.evaluate_hourly_rsi([])["status"] == "UNAVAILABLE"
    assert module.evaluate_hourly_rsi([{"close": float(i)} for i in range(1, 20)])["status"] == "READY"
    five_minute = module.evaluate_strategy_signals(history, "5m", {"price": 101, "volume": 2500})
    assert five_minute["daily"]["breakout_125d"]["status"] == "UNAVAILABLE"
    assert five_minute["execution_authorized"] is False
    print("STRATEGY SIGNALS SELF-TEST: PASS")

if __name__ == "__main__":
    main()
