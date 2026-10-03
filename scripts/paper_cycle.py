#!/usr/bin/env python3
"""Create an auditable, paper-only decision snapshot.

Pipeline responsibility:
Dhan snapshot -> deterministic SCRAP -> strategy evidence -> AI research
council context -> deterministic candidate/risk gates -> decision ledger.

AI analysis is advisory. It can challenge evidence, but it cannot bypass the
paper engine's data, capital, liquidity, risk or duplicate-order gates.
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from learning_policy import load_policy
except ImportError:
    load_policy = lambda: {}

SNAPSHOT = Path("public/data/market_snapshot.json")
SCRAP = Path("public/data/scrap_analysis.json")
COUNCIL = Path("public/data/ai_research_council.json")
CAPITAL = max(1000.0, float(os.getenv("PAPER_ANALYSIS_BUDGET", os.getenv("PAPER_REFERENCE_CAPITAL", "1000")) or 1000))
MAX_POSITION_PCT = float(os.getenv("PAPER_MAX_POSITION_PCT", "20"))
MIN_SCORE = float(os.getenv("PAPER_REVIEW_SCORE", "65"))
MIN_SCRAP_SCORE = float(os.getenv("PAPER_MIN_SCRAP_SCORE", "60"))


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
    change = num(stock.get("change"))
    groups = [
        {
            "id": "buffett", "name": "Warren Buffett", "focus": "Quality, moat, capital preservation",
            "checks": [
                check("ROIC / ROCE", num(stock.get("roic") or stock.get("roce")), lambda v: v >= 15),
                check("Free cash flow", num(stock.get("free_cash_flow") or stock.get("fcf")), lambda v: v > 0),
                check("Debt discipline", num(stock.get("debt_to_equity") or stock.get("debt_equity")), lambda v: v <= 1),
            ],
        },
        {
            "id": "jhunjhunwala", "name": "Jhunjhunwala", "focus": "Secular growth, earnings and operating leverage",
            "checks": [
                check("Earnings growth", num(stock.get("earnings_growth") or stock.get("profit_growth") or stock.get("eps_growth")), lambda v: v >= 15),
                check("Revenue growth", num(stock.get("revenue_growth") or stock.get("sales_growth")), lambda v: v >= 10),
                check("Sector growth", num(stock.get("sector_growth") or stock.get("sector_tailwind")), lambda v: v >= 10),
                check("Operating leverage", num(stock.get("operating_leverage")), lambda v: v > 0),
            ],
        },
        {
            "id": "lynch", "name": "Peter Lynch", "focus": "Growth versus valuation",
            "checks": [
                check("PEG", num(stock.get("peg") or stock.get("peg_ratio")), lambda v: 0 < v <= 1.5),
                check("Earnings growth", num(stock.get("earnings_growth") or stock.get("profit_growth") or stock.get("eps_growth")), lambda v: v >= 10),
                check("P/E", num(stock.get("pe") or stock.get("pe_ratio")), lambda v: 0 < v <= 35),
            ],
        },
        {
            "id": "hundred_baggers", "name": "100 Baggers", "focus": "Reinvestment and long growth runway",
            "checks": [
                check("ROIC / ROCE", num(stock.get("roic") or stock.get("roce")), lambda v: v >= 15),
                check("Reinvestment rate", num(stock.get("reinvestment_rate")), lambda v: v >= 10),
                check("Growth runway", num(stock.get("runway_years")), lambda v: v >= 5),
                check("Revenue growth", num(stock.get("revenue_growth") or stock.get("sales_growth")), lambda v: v >= 10),
            ],
        },
        {
            "id": "canslim", "name": "CANSLIM / O'Neil", "focus": "Growth, momentum and leadership",
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


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else fallback
    except (OSError, json.JSONDecodeError):
        return fallback


def quote_score(stock: dict) -> tuple[float, list[str]]:
    price = num(stock.get("price"))
    open_price = num(stock.get("open"))
    prev_close = num(stock.get("prev_close"))
    high = num(stock.get("high"))
    low = num(stock.get("low"))
    change = num(stock.get("change"))
    score = 50.0
    reasons: list[str] = []

    if price is None:
        return 0.0, ["price_unavailable"]
    if change is not None:
        if change > 0:
            score += min(change * 8.0, 20.0)
            reasons.append("positive_session_change")
        elif change < 0:
            score -= min(abs(change) * 8.0, 20.0)
            reasons.append("negative_session_change")

    intraday = pct(price, open_price)
    gap = pct(open_price, prev_close)
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
    if high is not None and low is not None and high > low:
        position = (price - low) / (high - low)
        if position >= 0.70:
            score += 5.0
            reasons.append("upper_range_position")
        elif position <= 0.30:
            score -= 5.0
            reasons.append("lower_range_position")
    return max(0.0, min(100.0, round(score, 2))), reasons


def score_stock(stock: dict, scrap_row: dict) -> tuple[float, list[str], str, dict]:
    qscore, quote_reasons = quote_score(stock)
    frameworks = evaluate_frameworks(stock)
    framework_passes = sum(1 for f in frameworks if f["status"] == "PASS")
    framework_available = sum(1 for f in frameworks if f["available"] > 0)
    framework_score = min(100.0, 50.0 + framework_passes * 10.0) if framework_available else 50.0

    scrap_status = scrap_row.get("status")
    scrap_score = num(scrap_row.get("score"))
    scrap_action = scrap_row.get("action") or "OBSERVE"

    reasons = list(quote_reasons)
    if scrap_status != "OK" or scrap_score is None:
        reasons.append("scrap_unavailable_or_insufficient")
        final_score = 0.55 * qscore + 0.15 * framework_score
        decision = "INSUFFICIENT_DATA"
    else:
        final_score = 0.65 * scrap_score + 0.25 * qscore + 0.10 * framework_score
        final_score = round(final_score, 2)
        reasons.append(f"scrap_{scrap_action.lower()}")
        if scrap_score >= MIN_SCRAP_SCORE and scrap_action == "REVIEW" and final_score >= MIN_SCORE:
            decision = "REVIEW"
            reasons.append("technical_scrap_gate_pass")
        elif scrap_score >= 50:
            decision = "WATCH"
            reasons.append("technical_scrap_watch")
        else:
            decision = "OBSERVE"
            reasons.append("technical_scrap_below_threshold")

    if framework_passes:
        reasons.append("strategy_framework_support")
    elif framework_available:
        reasons.append("strategy_framework_mixed_or_review")
    else:
        reasons.append("strategy_framework_evidence_unavailable")

    research = {
        "frameworks": frameworks,
        "scrap": scrap_row,
        "quote_score": qscore,
        "framework_score": framework_score,
    }
    return round(final_score, 2), reasons, decision, research


def main() -> int:
    if not SNAPSHOT.exists():
        raise SystemExit("Market snapshot is missing")

    snapshot = load_json(SNAPSHOT, {"status": "DATA_UNAVAILABLE", "stocks": []})
    scrap_data = load_json(SCRAP, {"status": "NOT_RUN", "stocks": []})
    council = load_json(COUNCIL, {"status": "NOT_RUN"})
    scrap_map = {row.get("symbol"): row for row in scrap_data.get("stocks", []) if row.get("symbol")}

    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%S")
    out = Path("data/ledger") / day / f"{stamp}.json"
    policy = load_policy()
    effective = policy.get("effective", {}) if isinstance(policy, dict) else {}
    global MIN_SCORE, MIN_SCRAP_SCORE
    MIN_SCORE = float(effective.get("review_score", MIN_SCORE))
    MIN_SCRAP_SCORE = float(effective.get("scrap_review_cutoff", MIN_SCRAP_SCORE))
    all_stocks = snapshot.get("stocks", [])
    analysis_budget = CAPITAL
    stocks = [
        stock for stock in all_stocks
        if num(stock.get("price")) is not None and num(stock.get("price")) <= analysis_budget
    ]
    regime = market_regime(stocks)
    max_position_value = round(CAPITAL * MAX_POSITION_PCT / 100.0, 2)

    ai_status = str(council.get("status", "NOT_RUN"))
    ai_consensus = council.get("consensus") if isinstance(council.get("consensus"), dict) else {}
    ai_classification = ai_consensus.get("classification")
    ai_available = ai_classification in {"SUPPORTS_REVIEW", "WATCH_ONLY", "NO_SUPPORT"} and ai_status in {
        "COMPLETE", "DEGRADED_ONE_AI", "DEGRADED_ONE_AI_FINAL"
    }

    candidates = []
    for stock in stocks:
        symbol = stock.get("symbol")
        scrap_row = scrap_map.get(symbol, {"symbol": symbol, "status": "UNAVAILABLE", "action": "OBSERVE", "score": None})
        score, factors, decision, research = score_stock(stock, scrap_row)
        rejection = None
        # AI is advisory per share. It can downgrade a deterministic REVIEW but can never create one or bypass gates.
        symbol_verdict = None
        verdict_row = council.get("candidate_verdicts", {}).get(symbol) if isinstance(council.get("candidate_verdicts"), dict) else None
        if isinstance(verdict_row, dict): symbol_verdict = verdict_row.get("verdict")
        if decision == "REVIEW" and ai_available:
            if ai_classification == "NO_SUPPORT" or symbol_verdict in {"WATCH", "AVOID"}:
                decision = "WATCH"
                factors.append("ai_symbol_" + str(symbol_verdict or ai_classification).lower())
            elif symbol_verdict == "SUPPORT":
                factors.append("ai_symbol_support")
            else:
                factors.append("ai_symbol_verdict_missing")
        elif decision == "REVIEW":
            factors.append("ai_advisory_unavailable_deterministic_path")

        if decision == "INSUFFICIENT_DATA":
            rejection = "SCRAP_DATA_UNAVAILABLE"
        elif decision == "WATCH":
            rejection = "SCRAP_WATCH_ONLY"
        elif decision == "OBSERVE":
            rejection = "SCRAP_BELOW_REVIEW_THRESHOLD"

        candidates.append({
            "symbol": symbol,
            "quote": {
                "price": stock.get("price"), "change": stock.get("change"),
                "open": stock.get("open"), "high": stock.get("high"),
                "low": stock.get("low"), "prev_close": stock.get("prev_close"),
                "volume": stock.get("volume"), "security_id": stock.get("security_id"),
            },
            "features": {
                "score": score,
                "factors": factors,
                "strategy_frameworks": research["frameworks"],
                "quote_score": research["quote_score"],
                "framework_score": research["framework_score"],
            },
            "indicators": {
                "intraday_return_pct": pct(num(stock.get("price")), num(stock.get("open"))),
                "gap_pct": pct(num(stock.get("open")), num(stock.get("prev_close"))),
                "scrap": scrap_row.get("indicators", {}),
            },
            "market_regime": regime,
            "scrap_result": scrap_row,
            "ranking": None,
            "analysis_pool_member": decision == "REVIEW",
            "decision": decision,
            "learning_policy": policy,
            "ai_symbol_verdict": symbol_verdict,
            "rejection_reason": rejection,
            "available_capital": CAPITAL,
            "required_capital": max_position_value,
            "risk_gate": "PAPER_ONLY_PASS",
            "capacity_gate": "PAPER_REFERENCE_CAPACITY",
            "ai_council": {
                "symbol_verdict": symbol_verdict,
                "status": council.get("status", "NOT_RUN"),
                "execution_authorized": False,
                "consensus": council.get("consensus"),
                "classification": ai_classification,
                "degraded_mode": bool(council.get("degraded_mode")),
                "working_provider": council.get("working_provider"),
                "cross_review_available": bool(council.get("cross_review")),
                "fallback_policy": "Any available AI may guide the paper decision; unavailable AI providers are ignored for the cycle; if no AI is available, deterministic analysis continues; deterministic gates remain mandatory.",
            },
            "execution": {
                "mode": "PAPER",
                "order_submitted": False,
                "reason": "PAPER_EXECUTION_PENDING_DETERMINISTIC_GATES",
            },
        })

    candidates.sort(key=lambda item: item["features"]["score"], reverse=True)
    for rank, item in enumerate(candidates, start=1):
        item["ranking"] = rank

    reason_counts = Counter(x["rejection_reason"] for x in candidates if x["rejection_reason"])
    ledger = {
        "schema_version": "4.0",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "mode": "PAPER",
        "stage": "DHAN_SNAPSHOT -> SCRAP_TECHNICAL -> STRATEGY_EVIDENCE -> AI_RESEARCH -> DETERMINISTIC_GATES",
        "market_data_status": snapshot.get("status"),
        "source": snapshot.get("source"),
        "snapshot_timestamp": snapshot.get("timestamp"),
        "snapshot_data_as_of": snapshot.get("data_as_of"),
        "review_score_threshold": MIN_SCORE,
        "scrap_score_threshold": MIN_SCRAP_SCORE,
        "scrap_status": scrap_data.get("status", "NOT_RUN"),
        "scrap_timestamp": scrap_data.get("timestamp"),
        "universe_count": len(stocks),
        "source_universe_count": len(all_stocks),
        "analysis_budget": analysis_budget,
        "budget_rule": "Dhan available funds when available; otherwise ₹1,000 paper minimum",
        "budget_excluded_count": len(all_stocks) - len(stocks),
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
            "scrap_is_deterministic_gate": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"Wrote {out} with {len(stocks)} observations and {ledger['review_candidates']} review candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
