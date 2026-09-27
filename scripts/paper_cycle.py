#!/usr/bin/env python3
"""Create an auditable, paper-only decision snapshot.

The script records the evidence available at decision time and applies only
universe-wide deterministic rules. It never submits broker orders and never
creates stock-specific exceptions.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT = Path("public/data/market_snapshot.json")
CAPITAL = float(os.getenv("PAPER_REFERENCE_CAPITAL", "1000"))
MAX_POSITION_PCT = float(os.getenv("PAPER_MAX_POSITION_PCT", "20"))
MIN_SCORE = float(os.getenv("PAPER_REVIEW_SCORE", "65"))


def num(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return (a - b) / b * 100.0


def score_stock(stock: dict) -> tuple[float, list[str], str]:
    price = num(stock.get("price"))
    open_price = num(stock.get("open"))
    prev_close = num(stock.get("prev_close"))
    high = num(stock.get("high"))
    low = num(stock.get("low"))
    change = num(stock.get("change"))

    reasons: list[str] = []
    score = 50.0

    intraday = pct(price, open_price)
    gap = pct(open_price, prev_close)
    if change is not None:
        if change > 0:
            score += min(change * 8.0, 20.0)
            reasons.append("positive_session_change")
        elif change < 0:
            score -= min(abs(change) * 8.0, 20.0)
            reasons.append("negative_session_change")

    if intraday is not None:
        if intraday > 0:
            score += min(intraday * 6.0, 15.0)
            reasons.append("price_above_open")
        else:
            score -= min(abs(intraday) * 6.0, 15.0)
            reasons.append("price_below_open")

    if gap is not None and gap > 0:
        score += min(gap * 2.0, 5.0)
        reasons.append("positive_gap")

    if high is not None and low is not None and high > low and price is not None:
        position = (price - low) / (high - low)
        if position >= 0.70:
            score += 5.0
            reasons.append("upper_range_position")
        elif position <= 0.30:
            score -= 5.0
            reasons.append("lower_range_position")

    score = max(0.0, min(100.0, round(score, 2)))
    if price is None:
        return score, reasons, "INSUFFICIENT_DATA"
    if score >= MIN_SCORE:
        return score, reasons, "REVIEW"
    return score, reasons, "OBSERVE"


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%S")
    out = Path("data/ledger") / day / f"{stamp}.json"
    stocks = snapshot.get("stocks", [])
    max_position_value = round(CAPITAL * MAX_POSITION_PCT / 100.0, 2)

    candidates = []
    for stock in stocks:
        score, factors, decision = score_stock(stock)
        candidates.append({
            "symbol": stock.get("symbol"),
            "quote": {
                "price": stock.get("price"),
                "change": stock.get("change"),
                "open": stock.get("open"),
                "high": stock.get("high"),
                "low": stock.get("low"),
                "prev_close": stock.get("prev_close"),
                "volume": stock.get("volume"),
                "security_id": stock.get("security_id"),
            },
            "features": {
                "score": score,
                "factors": factors,
            },
            "indicators": {
                "intraday_return_pct": pct(num(stock.get("price")), num(stock.get("open"))),
                "gap_pct": pct(num(stock.get("open")), num(stock.get("prev_close"))),
            },
            "market_regime": None,
            "scrap_result": None,
            "ranking": None,
            "analysis_pool_member": decision == "REVIEW",
            "decision": decision,
            "rejection_reason": None if decision == "REVIEW" else ("INSUFFICIENT_DATA" if decision == "INSUFFICIENT_DATA" else "BELOW_GENERALIZED_REVIEW_THRESHOLD"),
            "available_capital": CAPITAL,
            "required_capital": max_position_value,
            "risk_gate": "PAPER_ONLY_PASS",
            "capacity_gate": "PAPER_REFERENCE_CAPACITY",
            "ai_council": {
                "status": "NOT_CALLED",
                "openai": None,
                "anthropic": None,
                "cross_review": None,
                "consensus": None,
            },
            "execution": {
                "mode": "PAPER",
                "order_submitted": False,
                "reason": "PAPER_EXECUTION_ENGINE_NOT_YET_ENABLED",
            },
        })

    candidates.sort(key=lambda item: item["features"]["score"], reverse=True)
    for rank, item in enumerate(candidates, start=1):
        item["ranking"] = rank

    ledger = {
        "schema_version": "2.0",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "mode": "PAPER",
        "stage": "DETERMINISTIC_SCREENING",
        "market_data_status": snapshot.get("status"),
        "source": snapshot.get("source"),
        "snapshot_timestamp": snapshot.get("timestamp"),
        "universe_count": len(stocks),
        "review_candidates": sum(1 for x in candidates if x["decision"] == "REVIEW"),
        "candidates": candidates,
        "safety": {
            "live_orders_enabled": False,
            "stock_specific_learning_enabled": False,
            "auto_strategy_mutation_enabled": False,
            "ai_can_bypass_risk_gates": False,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"Wrote {out} with {len(stocks)} observations and {ledger['review_candidates']} review candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
