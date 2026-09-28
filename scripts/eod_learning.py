#!/usr/bin/env python3
"""Analyze paper observations plus broad-market EOD movers.

This report is diagnostic only. It identifies generalized patterns behind
missed opportunities without creating stock-specific rules or mutating the
strategy automatically.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

LEDGER_ROOT = Path("data/ledger")
MARKET_OPPORTUNITIES = Path("public/data/eod_market_opportunities.json")
OUT = Path("public/data/eod_report.json")
THRESHOLD = float(os.getenv("MISSED_MOVE_THRESHOLD_PCT", "1.0"))


def load_today() -> tuple[str, list[dict]]:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = LEDGER_ROOT / day
    rows: list[dict] = []
    if folder.exists():
        for path in sorted(folder.glob("*.json")):
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return day, rows


def price(item: dict) -> float | None:
    try:
        value = float(item.get("quote", {}).get("price"))
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def analyze_ledger(day: str, ledgers: list[dict]) -> tuple[list[dict], Counter[str], int]:
    by_symbol: dict[str, list[tuple[datetime, dict]]] = defaultdict(list)
    for ledger in ledgers:
        try:
            ts = datetime.fromisoformat(str(ledger["timestamp"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        for candidate in ledger.get("candidates", []):
            symbol = candidate.get("symbol")
            if symbol:
                by_symbol[str(symbol)].append((ts, candidate))

    misses: list[dict] = []
    reason_counts: Counter[str] = Counter()
    realized_candidates = 0
    for symbol, observations in by_symbol.items():
        observations.sort(key=lambda x: x[0])
        for index, (ts, current) in enumerate(observations):
            current_price = price(current)
            if current_price is None:
                continue
            future = [(future_ts, price(candidate)) for future_ts, candidate in observations[index + 1:]]
            future = [(future_ts, p) for future_ts, p in future if p is not None]
            if not future:
                continue
            max_future = max(future, key=lambda x: x[1])
            max_return = (max_future[1] - current_price) / current_price * 100.0
            if max_return < THRESHOLD:
                continue
            realized_candidates += 1
            decision = current.get("decision")
            if decision == "REVIEW":
                continue
            reason = current.get("rejection_reason") or "UNKNOWN"
            reason_counts[reason] += 1
            misses.append({
                "source": "paper_observation",
                "symbol": symbol,
                "decision_timestamp": ts.isoformat().replace("+00:00", "Z"),
                "decision": decision,
                "reason": reason,
                "decision_price": round(current_price, 4),
                "best_observed_future_price": round(max_future[1], 4),
                "best_forward_return_pct": round(max_return, 3),
                "generalized_factors": current.get("features", {}).get("factors", []),
            })
    return misses, reason_counts, realized_candidates


def load_external_movers() -> dict:
    if not MARKET_OPPORTUNITIES.exists():
        return {"status": "NOT_RUN", "stocks": []}
    try:
        value = json.loads(MARKET_OPPORTUNITIES.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"status": "INVALID", "stocks": []}
    except (OSError, json.JSONDecodeError):
        return {"status": "INVALID", "stocks": []}


def external_misses(movers: dict, evaluated_symbols: set[str]) -> list[dict]:
    misses: list[dict] = []
    if movers.get("status") != "READY":
        return misses
    for row in movers.get("stocks", []):
        symbol = str(row.get("symbol") or "")
        if not symbol or symbol in evaluated_symbols:
            continue
        move = row.get("change_pct")
        try:
            move_f = float(move)
        except (TypeError, ValueError):
            continue
        if abs(move_f) < THRESHOLD:
            continue
        misses.append({
            "source": "broad_market_eod_scan",
            "symbol": symbol,
            "decision_timestamp": movers.get("generated_at"),
            "decision": "NOT_EVALUATED",
            "reason": "NOT_IN_PAPER_CANDIDATE_UNIVERSE",
            "eod_price": row.get("price"),
            "prev_close": row.get("prev_close"),
            "eod_move_pct": move_f,
            "observable_evidence": {
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "volume": row.get("volume"),
            },
            "interpretation": "Material EOD mover was outside the paper engine's evaluated universe; this is a discovery signal, not proof of an executable missed trade.",
        })
    return misses


def analyze(day: str, ledgers: list[dict]) -> dict:
    ledger_misses, reason_counts, realized_candidates = analyze_ledger(day, ledgers)
    evaluated_symbols = {str(c.get("symbol")) for l in ledgers for c in l.get("candidates", []) if c.get("symbol")}
    movers = load_external_movers()
    market_misses = external_misses(movers, evaluated_symbols)
    all_misses = ledger_misses + market_misses

    if market_misses:
        reason_counts["NOT_IN_PAPER_CANDIDATE_UNIVERSE"] += len(market_misses)

    patterns = [
        {
            "pattern": reason,
            "occurrences": count,
            "action": "Review the generalized universe/threshold/feature interaction across multiple symbols; do not create a symbol-specific rule.",
        }
        for reason, count in reason_counts.most_common()
    ]

    return {
        "schema_version": "2.0",
        "status": "READY" if (ledgers or movers.get("status") == "READY") else "NOT_READY",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "trading_day_utc": day,
        "source_ledger_count": len(ledgers),
        "evaluated_symbol_count": len(evaluated_symbols),
        "broad_market_scan_status": movers.get("status"),
        "broad_market_mover_count": len(movers.get("stocks", [])),
        "profitable_forward_moves_in_ledger": realized_candidates,
        "missed_opportunities": all_misses,
        "general_patterns": patterns,
        "threshold_pct": THRESHOLD,
        "optimization_policy": {
            "stock_specific_rules_allowed": False,
            "automatic_strategy_mutation": False,
            "required_next_step": "Validate generalized proposals on multiple days and out-of-sample data before activation.",
        },
        "limitations": [
            "An EOD move is an opportunity/discovery signal, not proof that an executable trade existed at the decision price.",
            "Broad-market discovery currently uses EOD LTP/quote data; intraday reconstruction requires historical candles for each discovered symbol.",
            "The report never automatically changes strategy code.",
        ],
    }


def main() -> int:
    day, ledgers = load_today()
    report = analyze(day, ledgers)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}: {len(report['missed_opportunities'])} missed/discovery opportunities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
