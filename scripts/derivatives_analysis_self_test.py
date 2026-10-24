#!/usr/bin/env python3
"""Dependency-free self-tests for derivatives_analysis.py."""
from __future__ import annotations

import math
from derivatives_analysis import analyze_option_chain, black_scholes_greeks


def main() -> int:
    g = black_scholes_greeks(100, 100, 0.5, 0.2)
    assert 0 < g["call_delta"] < 1
    assert -1 < g["put_delta"] < 0
    assert g["gamma"] > 0 and g["vega"] > 0
    assert math.isfinite(g["call_theta_annual"])
    rows = [
        {"strike": 90, "call_oi": 100, "put_oi": 600, "call_iv": 20, "put_iv": 21, "years_to_expiry": 0.05},
        {"strike": 100, "call_oi": 200, "put_oi": 500, "call_iv": 22, "put_iv": 23, "years_to_expiry": 0.05},
        {"strike": 110, "call_oi": 800, "put_oi": 100, "call_iv": 25, "put_iv": 24, "years_to_expiry": 0.05},
    ]
    out = analyze_option_chain(rows, underlying="NIFTY", spot=100, as_of="2026-10-24T09:15:00+05:30", historical_iv=[10, 15, 20, 25, 30])
    assert out["status"] == "OK"
    assert out["pcr_oi"] == 1200 / 1100
    assert out["max_pain"] in (90, 100, 110)
    assert out["iv_rank"] is not None and out["iv_percentile"] is not None
    assert out["greeks"] is not None
    empty = analyze_option_chain([], underlying="NIFTY", spot=None, as_of="test")
    assert empty["status"] == "DATA_UNAVAILABLE" and empty["pcr_oi"] is None
    bad = analyze_option_chain([{"strike": 100, "put_oi": 5}], underlying="NIFTY", spot=100, as_of="test")
    assert bad["status"] == "PARTIAL" and bad["pcr_oi"] is None
    try:
        black_scholes_greeks(100, 100, 0, 0.2)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid expiry must fail")
    print("DERIVATIVES ANALYSIS SELF-TEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
