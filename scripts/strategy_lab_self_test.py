#!/usr/bin/env python3
"""Offline unit tests for strategy_lab.py. No network, credentials, or dependencies."""
from __future__ import annotations
import importlib.util
from pathlib import Path

path = Path(__file__).with_name("strategy_lab.py")
spec = importlib.util.spec_from_file_location("strategy_lab", path)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

def candles(n=260, start=100.0, step=0.25):
    rows=[]
    for i in range(n):
        close=start+i*step
        rows.append({"open":close-0.1,"high":close+0.5,"low":close-0.5,
                     "close":close,"volume":10000+(i%5)*100})
    return rows

def test_insufficient_history_fails_closed():
    assert lab.range_expansion(candles(10))["signal"] == "NO_SIGNAL"
    assert lab.trend_following(candles(30))["signal"] == "NO_SIGNAL"
    assert lab.classify_market_regime([100]*100)["regime"] == "UNAVAILABLE"

def test_trend_following_is_generic_and_bounded():
    out=lab.trend_following(candles())
    assert out["signal"] == "BUY", out
    assert 0 <= out["score"] <= 100
    assert out["execution_eligible"] is False

def test_momentum():
    out=lab.momentum(candles(),period=20,min_move_pct=2)
    assert out["signal"] == "BUY", out

def test_pair_signal_discloses_no_cointegration_test():
    a=[100+i*0.1 for i in range(80)]
    b=[90+i*0.1 for i in range(80)]
    a[-1]*=1.2
    out=lab.pair_spread_signal(a,b,min_observations=60)
    assert out["execution_eligible"] is False
    assert out.get("evidence",{}).get("cointegration_tested") is False

def test_rotation_ranks_available_horizons():
    out=lab.rank_industry_rotation({"A":{"1m":1,"3m":3,"6m":5},"B":{"1m":-1,"3m":None,"6m":-2}})
    assert out[0]["industry"] == "A"
    assert out[1]["horizons_available"] == 2

def test_delivery_requires_real_inputs():
    assert lab.delivery_accumulation(None, 20, 100, 50)["signal"] == "NO_SIGNAL"
    assert lab.delivery_accumulation(40, 20, 200, 100)["signal"] == "WATCH"

def test_consensus_conflict_reduces_score():
    results=[{"strategy":"a","signal":"BUY","score":80,"status":"RESEARCH_ONLY"},
             {"strategy":"b","signal":"SELL","score":80,"status":"RESEARCH_ONLY"}]
    out=lab.combine_strategy_evidence(results)
    assert out["consensus"] == "CONFLICT" and out["score"] == 40
    assert out["execution_eligible"] is False

if __name__ == "__main__":
    for fn in [test_insufficient_history_fails_closed,test_trend_following_is_generic_and_bounded,
               test_momentum,test_pair_signal_discloses_no_cointegration_test,
               test_rotation_ranks_available_horizons,test_delivery_requires_real_inputs,
               test_consensus_conflict_reduces_score]:
        fn()
    print("STRATEGY LAB SELF-TEST: PASS (7 scenarios)")
