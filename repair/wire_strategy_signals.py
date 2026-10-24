#!/usr/bin/env python3
"""Wire the frozen strategy evaluator into verified Patch 5 sources."""
from pathlib import Path

scrap_path = Path("scripts/scrap_analysis.py")
source = scrap_path.read_text(encoding="utf-8")

if "from zoneinfo import ZoneInfo" not in source:
    import_anchor = "from pathlib import Path\n"
    if import_anchor not in source:
        raise SystemExit("SCRAP import anchor missing")
    source = source.replace(import_anchor, import_anchor + "from zoneinfo import ZoneInfo\n", 1)

old_lookback = 'LOOKBACK_DAYS = int(os.getenv("SCRAP_LOOKBACK_DAYS", "45"))'
new_lookback = '# 260 calendar days generally cover 125 completed sessions plus holidays.\nLOOKBACK_DAYS = int(os.getenv("SCRAP_LOOKBACK_DAYS", "260"))'
if old_lookback in source:
    source = source.replace(old_lookback, new_lookback, 1)
if 'LOOKBACK_DAYS = int(os.getenv("SCRAP_LOOKBACK_DAYS", "260"))' not in source:
    raise SystemExit("SCRAP 125-day history lookback could not be configured")

anchor = '                row = analyse(symbol, quote, candles)\n'
if 'row["strategy_signals"] = evaluate_strategy_signals(' not in source:
    if anchor not in source:
        raise SystemExit("SCRAP strategy insertion anchor not found")
    inserted = '''                try:
                    from strategy_signals import evaluate_strategy_signals

                    strategy_candles = candles
                    if interval == "1d":
                        today_ist = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()

                        def _candle_day(value):
                            try:
                                if isinstance(value, (int, float)) or str(value).isdigit():
                                    stamp = float(value)
                                    if stamp > 10_000_000_000:
                                        stamp /= 1000.0
                                    return datetime.fromtimestamp(stamp, timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()
                                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                                if parsed.tzinfo is None:
                                    parsed = parsed.replace(tzinfo=timezone.utc)
                                return parsed.astimezone(ZoneInfo("Asia/Kolkata")).date()
                            except (TypeError, ValueError, OverflowError, OSError):
                                return None

                        # Only identified, completed daily candles may form the previous-125-session window.
                        strategy_candles = [
                            candle for candle in candles
                            if _candle_day(candle.get("timestamp")) is not None
                            and _candle_day(candle.get("timestamp")) < today_ist
                        ]
                    row["strategy_signals"] = evaluate_strategy_signals(
                        strategy_candles, interval, quote
                    )
                except Exception as strategy_exc:
                    row["strategy_signals"] = {
                        "version": "strategy-reference-v1",
                        "execution_authorized": False,
                        "status": "UNAVAILABLE",
                        "reason": str(strategy_exc),
                    }
'''
    source = source.replace(anchor, anchor + inserted, 1)
scrap_path.write_text(source, encoding="utf-8")

print("STRATEGY_PIPELINE_WIRING=PASS")
