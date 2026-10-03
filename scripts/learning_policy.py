#!/usr/bin/env python3
"""Bounded, auditable learning policy (the EOD -> bot feedback loop).
The EOD analysis finds shares that made money and were missed, classifies WHY, and (here) turns
repeated, cross-symbol reasons into small adjustments of GENERAL parameters. Rules:
* Only general parameters move: SCRAP review cutoff, final review score, number of shares sent to
 deep analysis. Never a symbol, never a sector, never a per-stock rule.
* Evidence gate: a reason must involve >= MIN_PATTERN_SYMBOLS distinct symbols in one session.
* Small steps (<= STEP per parameter per day), hard floor/ceiling, and a total drift cap from the
 configured base so the bot cannot slide into reckless settings.
* Two-sided: a losing day (net realized loss with >= 2 stop-losses) tightens the same parameters;
 loosening is blocked on any net-losing day.
* Idempotent per trading day, fully logged (policy["log"]), reversible by deleting the file or by
 LEARNING_ENABLED=0. Capital / risk / position limits are NEVER touched by learning.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
POLICY_PATH = Path("data/learning/policy.json")
MIN_PATTERN_SYMBOLS = int(os.getenv("MIN_PATTERN_SYMBOLS", "3"))
LOG_KEEP = 60
# name: (env var, base default, floor, ceiling, step)
PARAMS = {
 "scrap_review_cutoff": ("SCRAP_REVIEW_CUTOFF", 70.0, 60.0, 80.0, 1.0),
 "review_score": ("PAPER_REVIEW_SCORE", 65.0, 55.0, 75.0, 1.0),
 "universe_top_n": ("UNIVERSE_TOP_N", 60.0, 40.0, 100.0, 5.0),
}
MAX_DRIFT_FRACTION = 0.15 # never more than 15% away from the configured base
# Reason -> parameters to LOOSEN when the reason is a repeated cross-symbol miss.
LOOSEN = {
 "SCRAP_WATCH_ONLY": ("scrap_review_cutoff", "review_score"),
 "EXECUTION_FEATURE_SCORE_BELOW_THRESHOLD": ("review_score",),
 "NOT_IN_PAPER_CANDIDATE_UNIVERSE_WITH_RECONSTRUCTED_SETUP": ("universe_top_n",),
 "NOT_IN_PAPER_CANDIDATE_UNIVERSE_NO_RECONSTRUCTED_SETUP": ("universe_top_n",),
 "NOT_IN_PAPER_CANDIDATE_UNIVERSE_RECONSTRUCTION_UNAVAILABLE": ("universe_top_n",),
}
# Reasons that are reported but never auto-tuned (data / capital / capacity / risk problems).
REPORT_ONLY = {
 "SCRAP_BELOW_REVIEW_THRESHOLD", "SCRAP_DATA_UNAVAILABLE", "UNKNOWN",
 "EXECUTION_SCRAP_SCORE_BELOW_THRESHOLD", "EXECUTION_MAX_POSITIONS_REACHED", 
"EXECUTION_INSUFFICIENT_CAPITAL",
}
def enabled() -> bool:
 return os.getenv("LEARNING_ENABLED", "1") != "0"
def base_value(name: str) -> float:
 env, default, *_ = PARAMS[name]
 try:
 return float(os.getenv(env, "") or default)
 except ValueError:
 return float(default)
def load() -> dict:
 try:
 value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
 if isinstance(value, dict):
 value.setdefault("deltas", {})
 value.setdefault("log", [])
<PARSED TEXT FOR PAGE: 15 / 56>
 return value
 except (OSError, json.JSONDecodeError):
 pass
 return {"schema_version": "1.0", "deltas": {}, "log": [], "last_applied_day": None}
def _bounds(name: str) -> tuple[float, float]:
 _, _, floor, ceiling, _ = PARAMS[name]
 base = base_value(name)
 drift = abs(base) * MAX_DRIFT_FRACTION
 # Never clamp the configured base itself: an operator-chosen base outside the default
 # floor/ceiling stays valid; learning just cannot move further out than the limits allow.
 return min(max(floor, base - drift), base), max(min(ceiling, base + drift), base)
def effective(policy: dict | None = None) -> dict:
 """Effective parameter values = clamp(base + learned delta). Falls back to base if disabled."""
 policy = policy if policy is not None else load()
 out: dict = {}
 for name in PARAMS:
 base = base_value(name)
 delta = float((policy.get("deltas") or {}).get(name, 0.0)) if enabled() else 0.0
 lo, hi = _bounds(name)
 value = max(lo, min(hi, base + delta))
 out[name] = int(round(value)) if name == "universe_top_n" else round(value, 2)
 out["learning_enabled"] = enabled()
 out["source"] = "learned" if any((policy.get("deltas") or {}).values()) and enabled() else "base"
 return out
def save(policy: dict) -> None:
 POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
 policy["log"] = policy.get("log", [])[-LOG_KEEP:]
 tmp = POLICY_PATH.with_name(POLICY_PATH.name + ".tmp")
 tmp.write_text(json.dumps(policy, indent=2), encoding="utf-8")
 os.replace(tmp, POLICY_PATH)
def apply_learning(day: str, patterns: list[dict], day_stats: dict, policy: dict | None = None) -> dict:
 """Return {policy, changes, skipped}. Pure except for reading env; caller persists with save()."""
 policy = policy if policy is not None else load()
 changes: list[dict] = []
 skipped: list[dict] = []
 if not enabled():
 return {"policy": policy, "changes": [], "skipped": [{"reason": "LEARNING_ENABLED=0"}]}
 if policy.get("last_applied_day") == day:
 return {"policy": policy, "changes": [], "skipped": [{"reason": "already applied for " + day}]}
 pnl = float(day_stats.get("realized_pnl") or 0.0)
 stops = int(day_stats.get("stop_loss_exits") or 0)
 losing_day = pnl < 0
 tighten = losing_day and stops >= 2
 touched: dict[str, int] = {}
 def move(name: str, direction: int, why: str, evidence: dict) -> None:
 _, _, _, _, step = PARAMS[name]
 lo, hi = _bounds(name)
 # direction -1 loosens review thresholds (lower) but widens top_n (higher): normalise.
 sign = direction if name != "universe_top_n" else -direction
 current = float(policy["deltas"].get(name, 0.0))
 proposed = current + sign * step
 value = base_value(name) + proposed
 if value < lo or value > hi:
 skipped.append({"parameter": name, "reason": "at bound", "why": why})
 return
 if touched.get(name, 0) >= 1:
 skipped.append({"parameter": name, "reason": "already moved once today", "why": why})
 return
 policy["deltas"][name] = proposed
 touched[name] = 1
 changes.append({"parameter": name, "from": round(base_value(name) + current, 2), "to": round(value, 
2),
<PARSED TEXT FOR PAGE: 16 / 56>
 "why": why, "evidence": evidence})
 for pattern in patterns:
 reason = str(pattern.get("pattern"))
 distinct = int(pattern.get("distinct_symbols") or 0)
 evidence = {"pattern": reason, "distinct_symbols": distinct, "occurrences": 
pattern.get("occurrences")}
 if distinct < MIN_PATTERN_SYMBOLS:
 skipped.append({"pattern": reason, "reason": f"only {distinct} distinct symbols"})
 continue
 if reason in REPORT_ONLY:
 skipped.append({"pattern": reason, "reason": "report-only (not auto-tuned)"})
 continue
 targets = LOOSEN.get(reason)
 if not targets:
 skipped.append({"pattern": reason, "reason": "no general parameter maps to this reason"})
 continue
 if losing_day:
 skipped.append({"pattern": reason, "reason": f"loosening blocked: net realized P/L {pnl:.2f} < 
0"})
 continue
 for name in targets:
 move(name, -1, f"repeated cross-symbol miss: {reason}", evidence)
 if tighten:
 for name in ("scrap_review_cutoff", "review_score"):
 move(name, +1, f"losing day: realized P/L {pnl:.2f}, {stops} stop-loss exits",
 {"realized_pnl": pnl, "stop_loss_exits": stops})
 policy["last_applied_day"] = day
 policy["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
 policy["log"].append({"day": day, "changes": changes, "skipped": skipped[:20], "day_stats": day_stats})
 return {"policy": policy, "changes": changes, "skipped": skipped}