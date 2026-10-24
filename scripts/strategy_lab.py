#!/usr/bin/env python3
"""Research-only strategy primitives for MyTradeAnalysis.

This module evaluates generic OHLCV inputs. It does not place orders and does not
assume that a signal is profitable. Missing inputs produce NO_SIGNAL/UNAVAILABLE.
All strategies share a common output schema so the paper engine can integrate them
without stock-specific rules.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean, pstdev
from typing import Any, Iterable


def _num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _series(candles: Iterable[dict], field: str) -> list[float]:
    result = []
    for candle in candles:
        value = _num(candle.get(field))
        if value is not None:
            result.append(value)
    return result


def _result(strategy: str, signal: str = "NO_SIGNAL", reason: str = "Conditions not met",
            score: float = 0.0, entry: float | None = None,
            stop: float | None = None, target: float | None = None,
            evidence: dict | None = None) -> dict:
    return {
        "strategy": strategy, "signal": signal, "reason": reason,
        "score": round(max(0.0, min(100.0, score)), 2),
        "entry": entry, "stop_loss": stop, "target": target,
        "evidence": evidence or {},
        "execution_eligible": False,
        "status": "RESEARCH_ONLY",
    }


def _atr(candles: list[dict], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    tr = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        high, low, prev_close = _num(c.get("high")), _num(c.get("low")), _num(p.get("close"))
        if high is None or low is None or prev_close is None:
            continue
        tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return mean(tr[-period:]) if len(tr) >= period else None


def range_expansion(candles: list[dict], lookback: int = 20,
                    volume_multiple: float = 1.2, atr_multiple: float = 1.0) -> dict:
    """Breakout from a prior range with volume and range-expansion confirmation."""
    name = "range_expansion"
    if lookback < 2 or len(candles) < max(lookback + 1, 16):
        return _result(name, reason="INSUFFICIENT_HISTORY")
    prior = candles[-lookback-1:-1]
    highs, lows = _series(prior, "high"), _series(prior, "low")
    closes, volumes = _series(candles, "close"), _series(candles, "volume")
    high, low = (max(highs) if highs else None), (min(lows) if lows else None)
    close = closes[-1] if closes else None
    atr = _atr(candles)
    recent_range = _num(candles[-1].get("high"))
    recent_low = _num(candles[-1].get("low"))
    if None in (high, low, close, atr, recent_range, recent_low) or atr <= 0:
        return _result(name, reason="REQUIRED_OHLCV_UNAVAILABLE")
    avg_vol = mean(volumes[-21:-1]) if len(volumes) >= 21 else None
    current_vol = _num(candles[-1].get("volume"))
    vol_ok = avg_vol is not None and avg_vol > 0 and current_vol is not None and current_vol >= avg_vol * volume_multiple
    expanded = (recent_range - recent_low) >= atr * atr_multiple
    if close > high and vol_ok and expanded:
        entry = close
        stop = max(low, entry - 1.5 * atr)
        return _result(name, "BUY", "Prior-range breakout confirmed by volume and true range",
                       75, entry, stop, entry + 2 * (entry - stop),
                       {"prior_range_high": high, "prior_range_low": low, "atr": atr,
                        "volume_multiple": current_vol / avg_vol, "range_expanded": expanded})
    if close < low and vol_ok and expanded:
        entry = close
        stop = min(high, entry + 1.5 * atr)
        return _result(name, "SELL", "Prior-range breakdown confirmed by volume and true range",
                       75, entry, stop, entry - 2 * (stop - entry),
                       {"prior_range_high": high, "prior_range_low": low, "atr": atr,
                        "volume_multiple": current_vol / avg_vol, "range_expanded": expanded})
    return _result(name, reason="BREAKOUT_CONFIRMATION_NOT_MET",
                   evidence={"prior_range_high": high, "prior_range_low": low, "atr": atr,
                             "volume_confirmed": vol_ok, "range_expanded": expanded})


def trend_following(candles: list[dict], fast: int = 20, slow: int = 50,
                    momentum_period: int = 10) -> dict:
    """Moving-average trend alignment with momentum and ATR-based risk levels."""
    name = "trend_following"
    closes = _series(candles, "close")
    if fast < 2 or slow <= fast or len(closes) < max(slow, momentum_period + 1):
        return _result(name, reason="INSUFFICIENT_HISTORY")
    fma, sma = mean(closes[-fast:]), mean(closes[-slow:])
    momentum = (closes[-1] / closes[-1-momentum_period] - 1) * 100 if closes[-1-momentum_period] else None
    atr = _atr(candles)
    if momentum is None or atr is None or atr <= 0:
        return _result(name, reason="REQUIRED_DATA_UNAVAILABLE")
    close = closes[-1]
    if close > fma > sma and momentum > 0:
        return _result(name, "BUY", "Price and moving averages confirm positive trend",
                       min(90, 60 + momentum), close, close - 1.5 * atr, close + 3 * atr,
                       {"fast_average": fma, "slow_average": sma, "momentum_pct": momentum, "atr": atr})
    if close < fma < sma and momentum < 0:
        return _result(name, "SELL", "Price and moving averages confirm negative trend",
                       min(90, 60 + abs(momentum)), close, close + 1.5 * atr, close - 3 * atr,
                       {"fast_average": fma, "slow_average": sma, "momentum_pct": momentum, "atr": atr})
    return _result(name, reason="TREND_ALIGNMENT_NOT_MET",
                   evidence={"fast_average": fma, "slow_average": sma, "momentum_pct": momentum})


def momentum(candles: list[dict], period: int = 20, min_move_pct: float = 2.0) -> dict:
    """Generic lookback momentum signal; thresholds are configurable, not stock-specific."""
    name = "momentum"
    closes = _series(candles, "close")
    if period < 1 or len(closes) <= period:
        return _result(name, reason="INSUFFICIENT_HISTORY")
    base, close = closes[-1-period], closes[-1]
    if base <= 0:
        return _result(name, reason="INVALID_BASE_PRICE")
    move = (close / base - 1) * 100
    if move >= min_move_pct:
        return _result(name, "BUY", "Positive lookback momentum threshold met",
                       min(90, 60 + abs(move)), close, None, None, {"return_pct": move, "period": period})
    if move <= -min_move_pct:
        return _result(name, "SELL", "Negative lookback momentum threshold met",
                       min(90, 60 + abs(move)), close, None, None, {"return_pct": move, "period": period})
    return _result(name, reason="MOMENTUM_THRESHOLD_NOT_MET", evidence={"return_pct": move, "period": period})


def mean_reversion(candles: list[dict], period: int = 20, z_threshold: float = 2.0) -> dict:
    """Research signal based on rolling close-price z-score; no signal in a strong trend filter."""
    name = "mean_reversion"
    closes = _series(candles, "close")
    if period < 5 or len(closes) < period + 1:
        return _result(name, reason="INSUFFICIENT_HISTORY")
    window = closes[-period:]
    sd = pstdev(window)
    if sd <= 0:
        return _result(name, reason="ZERO_VARIANCE")
    z = (closes[-1] - mean(window)) / sd
    close = closes[-1]
    if z <= -abs(z_threshold):
        return _result(name, "BUY", "Price is statistically below its rolling mean",
                       min(85, 55 + abs(z) * 10), close, None, mean(window),
                       {"z_score": z, "rolling_mean": mean(window), "std_dev": sd})
    if z >= abs(z_threshold):
        return _result(name, "SELL", "Price is statistically above its rolling mean",
                       min(85, 55 + abs(z) * 10), close, None, mean(window),
                       {"z_score": z, "rolling_mean": mean(window), "std_dev": sd})
    return _result(name, reason="Z_SCORE_WITHIN_THRESHOLD", evidence={"z_score": z})


def pair_spread_signal(series_a: list[float], series_b: list[float],
                       z_threshold: float = 2.0, min_observations: int = 60) -> dict:
    """Exploratory spread z-score only; this does NOT establish cointegration."""
    name = "pair_spread"
    if len(series_a) != len(series_b) or len(series_a) < min_observations:
        return _result(name, reason="INSUFFICIENT_ALIGNED_HISTORY")
    if any(_num(x) is None or x <= 0 for x in series_a + series_b):
        return _result(name, reason="INVALID_PAIR_PRICES")
    spreads = [__import__("math").log(a) - __import__("math").log(b) for a, b in zip(series_a, series_b)]
    window = spreads[-min_observations:]
    sd = pstdev(window)
    if sd <= 0:
        return _result(name, reason="ZERO_SPREAD_VARIANCE")
    z = (spreads[-1] - mean(window)) / sd
    if z >= abs(z_threshold):
        return _result(name, "SHORT_A_LONG_B", "Spread above threshold; exploratory pair signal",
                       min(85, 55 + abs(z) * 10), evidence={"z_score": z, "alpha": mean(window),
                       "cointegration_tested": False})
    if z <= -abs(z_threshold):
        return _result(name, "LONG_A_SHORT_B", "Spread below threshold; exploratory pair signal",
                       min(85, 55 + abs(z) * 10), evidence={"z_score": z, "alpha": mean(window),
                       "cointegration_tested": False})
    return _result(name, evidence={"z_score": z, "cointegration_tested": False})


def classify_market_regime(index_closes: list[float], breadth_above_200dma_pct: float | None = None) -> dict:
    """Broad defensive/neutral/risk-on context; it never creates a trade by itself."""
    closes = [_num(x) for x in index_closes]
    closes = [x for x in closes if x is not None]
    if len(closes) < 200:
        return {"regime": "UNAVAILABLE", "reason": "NEED_200_DAILY_CLOSES", "execution_eligible": False}
    dma50, dma200, last = mean(closes[-50:]), mean(closes[-200:]), closes[-1]
    breadth = _num(breadth_above_200dma_pct)
    if last < dma200 and (breadth is None or breadth < 40):
        regime = "DEFENSIVE_RISK_OFF"
    elif last > dma200 and last > dma50 and (breadth is None or breadth >= 55):
        regime = "RISK_ON"
    else:
        regime = "MIXED_NEUTRAL"
    return {"regime": regime, "close": last, "dma50": dma50, "dma200": dma200,
            "breadth_above_200dma_pct": breadth, "execution_eligible": False}


def rank_industry_rotation(industry_returns: dict[str, dict[str, float | None]]) -> list[dict]:
    """Rank industries on available 1M/3M/6M returns without inventing missing horizons."""
    rows = []
    for industry, horizons in industry_returns.items():
        vals = {k: _num(horizons.get(k)) for k in ("1m", "3m", "6m")}
        available = [v for v in vals.values() if v is not None]
        if not available:
            continue
        # Equal-weight only available horizons and disclose coverage.
        score = mean(available)
        rows.append({"industry": industry, "score": round(score, 4),
                     "returns_pct": vals, "horizons_available": len(available)})
    return sorted(rows, key=lambda x: (-x["score"], x["industry"].casefold()))


def delivery_accumulation(delivery_pct: float | None, delivery_avg_pct: float | None,
                          turnover: float | None, turnover_avg: float | None) -> dict:
    """Flag unusual delivery-backed activity; input feed must be verified by caller."""
    name = "delivery_accumulation"
    dp, dap, tv, tav = map(_num, (delivery_pct, delivery_avg_pct, turnover, turnover_avg))
    if None in (dp, dap, tv, tav) or dap <= 0 or tav <= 0:
        return _result(name, reason="DELIVERY_OR_TURNOVER_DATA_UNAVAILABLE")
    delivery_multiple, turnover_multiple = dp / dap, tv / tav
    if delivery_multiple >= 1.25 and turnover_multiple >= 1.5:
        return _result(name, "WATCH", "Delivery share and turnover are both elevated",
                       65, evidence={"delivery_multiple": delivery_multiple,
                                     "turnover_multiple": turnover_multiple})
    return _result(name, reason="ACCUMULATION_THRESHOLDS_NOT_MET",
                   evidence={"delivery_multiple": delivery_multiple, "turnover_multiple": turnover_multiple})


def combine_strategy_evidence(results: list[dict]) -> dict:
    """Aggregate research evidence; conflicting signals reduce confidence, never bypass risk gates."""
    usable = [r for r in results if r.get("status") == "RESEARCH_ONLY" and r.get("signal") not in ("NO_SIGNAL", "WATCH")]
    if not usable:
        return {"consensus": "NO_SIGNAL", "score": 0.0, "signals": [], "execution_eligible": False}
    directions = {r["signal"] for r in usable}
    if directions == {"BUY"}:
        consensus = "BUY"
    elif directions == {"SELL"}:
        consensus = "SELL"
    else:
        consensus = "CONFLICT"
    score = mean(float(r.get("score", 0)) for r in usable)
    if consensus == "CONFLICT":
        score *= 0.5
    return {"consensus": consensus, "score": round(score, 2),
            "signals": [r["strategy"] + ":" + r["signal"] for r in usable],
            "execution_eligible": False,
            "reason": "Research-only consensus; backtest, data freshness, costs, risk and broker gates remain mandatory."}
