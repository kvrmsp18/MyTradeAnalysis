#!/usr/bin/env python3
"""Create an auditable, paper-only decision snapshot.

The decision ledger records the evidence available at decision time. Strategy
frameworks are generalized research factors only; they never create symbol-
specific exceptions and they never bypass deterministic safety gates.
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT = Path("public/data/market_snapshot.json")
COUNCIL = Path("public/data/ai_research_council.json")
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


def check(name: str, value: float | None, predicate) -> dict:
    if value is None:
        return {"name": name, "state": "UNAVAILABLE", "value": None}
    return {"name": name, "state": "PASS" if predicate(value) else "REVIEW", "value": value}


def evaluate_frameworks(stock: dict) -> list[dict]:
    """Evaluate only evidence actually present in the market snapshot.

    Fundamental fields may be unavailable in the current Dhan LTP snapshot.
    They are explicitly marked unavailable rather than guessed.
    """
    change = num(stock.get("change"))
    price = num(stock.get("price"))
    open_price = num(stock.get("open"))
    prev_close = num(stock.get("prev_close"))
    volume = num(stock.get("volume"))

    intraday = pct(price, open_price)
    gap = pct(open_price, prev_close)

    # Only generic, evidence-backed checks are used here. Missing fundamentals
    # do not become synthetic scores.
    groups = [
        {
            "id": "buffett",
            "name": "Warren Buffett",
            "focus": "Quality, moat, capital preservation",
            "checks": [
                check("ROIC / ROCE", num(stock.get("roic") or stock.get("roce")), lambda v: v >= 15),
                check("Free cash flow", num(stock.get("free_cash_flow") or stock.get("fcf")), lambda v: v > 0),
                check("Debt discipline", num(stock.get("debt_to_equity") or stock.get("debt_equity")), lambda v: v <= 1),
            ],
        },
        {
            "id": "jhunjhunwala",
            "name": "Jhunjhunwala",
            "focus": "Secular growth, earnings and operating leverage",
            "checks": [
                check("Earnings growth", num(stock.get("earnings_growth") or stock.get("profit_growth") or stock.get("eps_growth")), lambda v: v >= 15),
                check("Revenue growth", num(stock.get("revenue_growth") or stock.get("sales_growth")), lambda v: v >= 10),
                check("Sector growth", num(stock.get("sector_growth") or stock.get("sector_tailwind")), lambda v: v >= 10),
                check("Operating leverage", num(stock.get("operating_leverage")), lambda v: v > 0),
            ],
        },
        {
            "id": "lynch",
            "name": "Peter Lynch",
            "focus": "Growth versus valuation",
            "checks": [
                check("PEG", num(stock.get("peg") or stock.get("peg_ratio")), lambda v: 0 < v <= 1.5),
                check("Earnings growth", num(stock.get("earnings_growth") or stock.get("profit_growth") or stock.get("eps_growth")), lambda v: v >= 10),
                check("P/E", num(stock.get("pe") or stock.get("pe_ratio")), lambda v: 0 < v <= 35),
            ],
        },
        {
            "id": "hundred_baggers",
            "name": "100 Baggers",
            "focus": "Reinvestment and long growth runway",
            "checks": [
                check("ROIC / ROCE", num(stock.get("roic") or stock.get("roce")), lambda v: v >= 15),
                check("Reinvestment rate", num(stock.get("reinvestment_rate")), lambda v: v >= 10),
                check("Growth runway", num(stock.get("runway_years")), lambda v: v >= 5),
                check("Revenue growth", num(stock.get("revenue_growth") or stock.get("sales_growth")), lambda v: v >= 10),
            ],
        },
        {
            "id": "canslim",
            "name": "CANSLIM / O'Neil",
            "focus": "Growth, momentum and leadership",
            "checks": [
                check("EPS growth", num(stock.get("eps_growth") or stock.get("earnings_growth")), lambda v: v >= 20),
                check("Sales growth", num(stock.get("sales_growth") or stock.get("revenue_growth")), lambda v: v >= 10),
                check("Price momentum", num(stock.get("price_change_20d") or stock.get("change_20d") or change), lambda v: v > 0),
                check("Relative strength", num(stock.get("relative_strength") or stock.get("rs_rating")), lambda v: v >= 70),
                check("Volume confirmation", num(stock.get("volume_ratio") or stock.get("volume_vs_average")), lambda v: v >= 1.2),
            ],
        },
    ]

    for group in groups:
        available = [x for x in group["checks"] if x["state"] != "UNAVAILABLE"]
        passed = [x for x in available if x["state"] == "PASS"]
        group["available"] = len(available)
        group["passed"] = len(passed)
        group["total"] = len(group["checks"])
        group["evidence_completeness_pct"] = round(len(available) / len(group["checks"]) * 100)
        group["status"] = (
            "UNAVAILABLE" if not available else
            "PARTIAL" if len(available) < len(group["checks"]) else
            "PASS" if len(passed) >= math.ceil(len(group["checks"]) * 0.6) else "REVIEW"
        )
    return groups


def score_stock(stock: dict) -> tuple[float, list[str], str, dict]:
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

    frameworks = evaluate_frameworks(stock)
    # Framework evidence is a small generalized research component. It cannot
    # manufacture unavailable fundamentals and cannot override risk gates.
    framework_passes = sum(1 for f in frameworks if f["status"] == "PASS")
    framework_available = sum(1 for f in frameworks if f["available"] > 0)
    if framework_passes:
        score += min(framework_passes * 2.0, 8.0)
        reasons.append("strategy_framework_support")
    elif framework_available:
        reasons.append("strategy_framework_mixed_or_review")
    else:
        reasons.append("strategy_framework_evidence_unavailable")

    score = max(0.0, min(100.0, round(score, 2)))
    if price is None:
        return score, reasons, "INSUFFICIENT_DATA", {"frameworks": frameworks}
    if score >= MIN_SCORE:
        return score, reasons, "REVIEW", {"frameworks": frameworks}
    return score, reasons, "OBSERVE", {"frameworks": frameworks}


def load_council() -> dict:
    if not COUNCIL.exists():
        return {"status": "NOT_RUN"}
    try:
        return json.loads(COUNCIL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "UNAVAILABLE"}


def market_regime(stocks: list[dict]) -> dict:
    changes = [num(s.get("change")) for s in stocks]
    changes = [x for x in changes if x is not None]
    if not changes:
        return {"status": "UNAVAILABLE", "confidence": 0}
    positive = sum(1 for x in changes if x > 0)
    breadth = positive / len(changes)
    if breadth >= 0.65:
        label = "BULLISH"
    elif breadth <= 0.35:
        label = "BEARISH"
    else:
        label = "MIXED"
    return {"status": label, "breadth_pct": round(breadth * 100, 1), "confidence": round(abs(breadth - 0.5) * 200, 1)}


def main() -> int:
    if not SNAPSHOT.exists():
        raise SystemExit("Market snapshot is missing")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%S")
    out = Path("data/ledger") / day / f"{stamp}.json"
    stocks = snapshot.get("stocks", [])
    council = load_council()
    regime = market_regime(stocks)
    max_position_value = round(CAPITAL * MAX_POSITION_PCT / 100.0, 2)

    candidates = []
    for stock in stocks:
        score, factors, decision, research = score_stock(stock)
        candidates.append({
            "symbol": stock.get("symbol"),
            "quote": {
                "price": stock.get("price"), "change": stock.get("change"),
                "open": stock.get("open"), "high": stock.get("high"),
                "low": stock.get("low"), "prev_close": stock.get("prev_close"),
                "volume": stock.get("volume"), "security_id": stock.get("security_id"),
            },
            "features": {"score": score, "factors": factors, "strategy_frameworks": research["frameworks"]},
            "indicators": {
                "intraday_return_pct": pct(num(stock.get("price")), num(stock.get("open"))),
                "gap_pct": pct(num(stock.get("open")), num(stock.get("prev_close"))),
            },
            "market_regime": regime,
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
                "status": council.get("status", "NOT_RUN"),
                "execution_authorized": False,
                "consensus": council.get("consensus"),
                "cross_review_available": bool(council.get("cross_review")),
            },
            "execution": {"mode": "PAPER", "order_submitted": False, "reason": "PAPER_EXECUTION_ENGINE_NOT_YET_ENABLED"},
        })

    candidates.sort(key=lambda item: item["features"]["score"], reverse=True)
    for rank, item in enumerate(candidates, start=1):
        item["ranking"] = rank

    reason_counts = Counter(x["rejection_reason"] for x in candidates if x["rejection_reason"])
    ledger = {
        "schema_version": "3.0",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "mode": "PAPER",
        "stage": "DETERMINISTIC_SCREENING_WITH_STRATEGY_EVIDENCE",
        "market_data_status": snapshot.get("status"),
        "source": snapshot.get("source"),
        "snapshot_timestamp": snapshot.get("timestamp"),
        "universe_count": len(stocks),
        "review_candidates": sum(1 for x in candidates if x["decision"] == "REVIEW"),
        "rejection_summary": dict(reason_counts),
        "market_regime": regime,
        "strategy_frameworks_enabled": ["buffett", "jhunjhunwala", "lynch", "hundred_baggers", "canslim"],
        "ai_council_status": council.get("status", "NOT_RUN"),
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
