#!/usr/bin/env python3
"""Deterministic, research-only NSE derivatives analytics.

This module never places orders and never turns an analytics label into an
execution instruction. Inputs must come from a timestamped, licensed market
data source. Missing values remain unavailable rather than being guessed.
"""
from __future__ import annotations

import math
from typing import Any, Iterable


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes_greeks(
    spot: float, strike: float, years_to_expiry: float, volatility: float,
    risk_free_rate: float = 0.06, dividend_yield: float = 0.0,
) -> dict[str, float | str]:
    """European-option Black-Scholes Greeks; rates/yields are annual decimals.

    Gamma and Vega are per one underlying unit; Vega is per 1.00 volatility
    change (divide by 100 for a one-volatility-point approximation).
    Theta is per calendar year (divide by 365 for an approximate daily value).
    """
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if years_to_expiry <= 0:
        raise ValueError("years_to_expiry must be positive")
    if volatility <= 0:
        raise ValueError("volatility must be positive")
    root_t = math.sqrt(years_to_expiry)
    d1 = (math.log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility**2) * years_to_expiry) / (volatility * root_t)
    d2 = d1 - volatility * root_t
    discount_q = math.exp(-dividend_yield * years_to_expiry)
    discount_r = math.exp(-risk_free_rate * years_to_expiry)
    gamma = discount_q * _pdf(d1) / (spot * volatility * root_t)
    vega = spot * discount_q * _pdf(d1) * root_t
    common_theta = -(spot * discount_q * _pdf(d1) * volatility) / (2.0 * root_t)
    call_delta = discount_q * _cdf(d1)
    put_delta = discount_q * (_cdf(d1) - 1.0)
    call_theta = common_theta - risk_free_rate * strike * discount_r * _cdf(d2) + dividend_yield * spot * discount_q * _cdf(d1)
    put_theta = common_theta + risk_free_rate * strike * discount_r * _cdf(-d2) - dividend_yield * spot * discount_q * _cdf(-d1)
    return {
        "call_delta": call_delta,
        "put_delta": put_delta,
        "gamma": gamma,
        "vega": vega,
        "call_theta_annual": call_theta,
        "put_theta_annual": put_theta,
        "d1": d1,
        "d2": d2,
    }


def _max_pain(rows: list[dict[str, Any]]) -> float | None:
    strikes = sorted({_number(row.get("strike")) for row in rows if _number(row.get("strike")) is not None})
    if not strikes:
        return None
    best_strike, best_payout = None, float("inf")
    for settlement in strikes:
        payout = 0.0
        for row in rows:
            strike = _number(row.get("strike"))
            call_oi = max(0.0, _number(row.get("call_oi")) or 0.0)
            put_oi = max(0.0, _number(row.get("put_oi")) or 0.0)
            if strike is None:
                continue
            payout += max(0.0, settlement - strike) * call_oi
            payout += max(0.0, strike - settlement) * put_oi
        if payout < best_payout:
            best_strike, best_payout = settlement, payout
    return best_strike


def analyze_option_chain(
    rows: Iterable[dict[str, Any]],
    *,
    underlying: str,
    spot: float | None,
    as_of: str,
    historical_iv: Iterable[float] | None = None,
) -> dict[str, Any]:
    """Summarize a normalized call/put OI chain without generating trade orders.

    Each row may include strike, call_oi, put_oi, call_volume, put_volume,
    call_iv, put_iv, call_ltp, put_ltp. Values are expected to be from the
    same expiry and observation time.
    """
    chain = [dict(row) for row in rows]
    base = {
        "schema_version": "1.0", "underlying": str(underlying).upper(),
        "as_of": as_of, "spot": spot, "status": "DATA_UNAVAILABLE",
        "row_count": len(chain), "pcr_oi": None, "pcr_volume": None,
        "max_pain": None, "iv_mean": None, "iv_rank": None,
        "iv_percentile": None, "bias": "UNAVAILABLE",
        "bias_reason": "No usable option-chain data.",
        "greeks": None, "limitations": [
            "Analytics only; not a buy/sell recommendation.",
            "PCR and max pain are descriptive, not reliable standalone predictors.",
            "Greeks require a valid expiry and volatility; stale or mismatched data invalidates results.",
        ],
    }
    if not chain:
        return base
    call_oi = sum(max(0.0, _number(r.get("call_oi")) or 0.0) for r in chain)
    put_oi = sum(max(0.0, _number(r.get("put_oi")) or 0.0) for r in chain)
    call_vol = sum(max(0.0, _number(r.get("call_volume")) or 0.0) for r in chain)
    put_vol = sum(max(0.0, _number(r.get("put_volume")) or 0.0) for r in chain)
    iv_values = [
        v for r in chain for v in (_number(r.get("call_iv")), _number(r.get("put_iv")))
        if v is not None and 0 < v <= 500
    ]
    hist = [v for v in (_number(x) for x in (historical_iv or [])) if v is not None and 0 <= v <= 500]
    iv_mean = sum(iv_values) / len(iv_values) if iv_values else None
    iv_rank = None
    iv_percentile = None
    if iv_mean is not None and hist:
        low, high = min(hist), max(hist)
        iv_rank = 100.0 * (iv_mean - low) / (high - low) if high > low else None
        iv_percentile = 100.0 * sum(v <= iv_mean for v in hist) / len(hist)
    pcr_oi = put_oi / call_oi if call_oi > 0 else None
    pcr_volume = put_vol / call_vol if call_vol > 0 else None
    pain = _max_pain(chain)
    usable_spot = _number(spot)
    if usable_spot is not None and usable_spot > 0 and pcr_oi is not None:
        if pcr_oi >= 1.2:
            bias, reason = "PUT_OI_HEAVY", "Put open interest is materially higher than call open interest; direction is not guaranteed."
        elif pcr_oi <= 0.8:
            bias, reason = "CALL_OI_HEAVY", "Call open interest is materially higher than put open interest; direction is not guaranteed."
        else:
            bias, reason = "BALANCED_OI", "Put-call open interest is within the configured neutral band."
    else:
        bias, reason = "UNAVAILABLE", "Spot or usable call open interest is missing."
    nearest = None
    if usable_spot is not None and usable_spot > 0:
        valid = [(abs((_number(r.get("strike")) or 0) - usable_spot), r) for r in chain if (_number(r.get("strike")) or 0) > 0]
        if valid:
            nearest = min(valid, key=lambda x: x[0])[1]
    greeks = None
    if nearest and usable_spot:
        strike = _number(nearest.get("strike"))
        vol_raw = _number(nearest.get("call_iv"))
        years = _number(nearest.get("years_to_expiry"))
        if strike and vol_raw and years and vol_raw > 0 and years > 0:
            greeks = black_scholes_greeks(usable_spot, strike, years, vol_raw / 100.0)
    base.update({
        "status": "OK" if pcr_oi is not None else "PARTIAL",
        "pcr_oi": round(pcr_oi, 4) if pcr_oi is not None else None,
        "pcr_volume": round(pcr_volume, 4) if pcr_volume is not None else None,
        "max_pain": pain, "iv_mean": round(iv_mean, 4) if iv_mean is not None else None,
        "iv_rank": round(iv_rank, 2) if iv_rank is not None else None,
        "iv_percentile": round(iv_percentile, 2) if iv_percentile is not None else None,
        "bias": bias, "bias_reason": reason, "greeks": greeks,
        "open_interest": {"call": call_oi, "put": put_oi},
        "volume": {"call": call_vol, "put": put_vol},
    })
    return base
