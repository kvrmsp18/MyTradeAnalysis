#!/usr/bin/env python3
"""Analyze the day's paper observations for generalized missed opportunities.

This report is deliberately diagnostic. It never changes strategy code, never
creates stock-specific rules, and never treats a future profitable move as a
trade that was guaranteed to be executable.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

LEDGER_ROOT = Path("data/ledger")
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


def analyze(day: str, ledgers: list[dict]) -> dict:
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

    misses = []
    realized_candidates = 0
    reason_counts: Counter[str] = Counter()

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
                "symbol": symbol,
                "decision_timestamp": ts.isoformat().replace("+00:00", "Z"),
                "decision": decision,
                "reason": reason,
                "decision_price": round(current_price, 4),
                "best_observed_future_price": round(max_future[1], 4),
                "best_forward_return_pct": round(max_return, 3),
                "generalized_factors": current.get("features", {}).get("factors", []),
            })

    patterns = [
        {
            "pattern": reason,
            "occurrences": count,
            "action": "Review the generalized threshold/feature interaction across the full universe; do not create a symbol-specific rule.",
        }
        for reason, count in reason_counts.most_common()
    ]

    return {
        "schema_version": "1.0",
        "status": "READY" if ledgers else "NOT_READY",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "trading_day_utc": day,
        "source_ledger_count": len(ledgers),
        "profitable_moves": realized_candidates,
        "missed_opportunities": misses,
        "general_patterns": patterns,
        "threshold_pct": THRESHOLD,
        "optimization_policy": {
            "stock_specific_rules_allowed": False,
            "automatic_strategy_mutation": False,
            "required_next_step": "Validate any generalized proposal on out-of-sample data before activation.",
        },
        "limitations": [
            "A forward price move is an opportunity signal, not proof that an executable trade existed at the exact decision price.",
            "The current report uses only observations persisted by the paper pipeline.",
            "No strategy change is applied automatically.",
        ],
    }


def main() -> int:
    day, ledgers = load_today()
    report = analyze(day, ledgers)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}: {report['profitable_moves']} profitable forward moves, {len(report['missed_opportunities'])} generalized misses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
