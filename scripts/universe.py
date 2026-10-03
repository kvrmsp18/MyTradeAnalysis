#!/usr/bin/env python3
"""Dynamic NSE equity universe. There is NO hard-coded share list anywhere in the bot.
Flow
 1. The full list of NSE cash-equity instruments comes from Dhan's public instrument master
 (cached in data/universe/nse_equity.json, refreshed daily).
 2. Every cycle the whole list is quoted live (Dhan /marketfeed/quote, 1000 ids per request) and
 ranked with ONE generic rule set: liquidity (turnover), momentum (% change) and intraday
 range. The top N (default 60, adjustable by the EOD learning loop) go to deep analysis.
 3. The selection is remembered (data/universe/last_selected.json) so that, if the live
 full-market feed is down, the fallback quote sources (NSE / Yahoo) still work on a list
 that was itself discovered from the live market, never on a typed-in list.
 4. If Dhan has never worked, the previous session's NSE bhavcopy (all EQ shares, one CSV) can
 bootstrap the same ranking.
Nothing here knows any company name. Ranking is purely numeric and percentile based.
"""
from __future__ import annotations
import csv
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
BHAVCOPY_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
CACHE_DIR = Path("data/universe")
MASTER_CACHE = CACHE_DIR / "nse_equity.json"
LAST_SELECTED = CACHE_DIR / "last_selected.json"
MASTER_MAX_AGE_HOURS = 20
CARRY_MAX_AGE_DAYS = 3
DEFAULT_TOP_N = 60
MIN_PRICE = 5.0 # sub-Rs5 shares are not tradeable intraday in a sane way (spread/tick dominates)
Fetch = Callable[[str], bytes]
def now_utc() -> datetime:
 return datetime.now(timezone.utc)
def iso(ts: datetime) -> str:
 return ts.isoformat().replace("+00:00", "Z")
def _pick(row: dict, *names: str) -> str:
 lowered = {str(k).strip().lower(): v for k, v in row.items()}
 for name in names:
 value = lowered.get(name.lower())
 if value not in (None, ""):
 return str(value).strip()
 return ""
def _num(value: object) -> float | None:
 try:
 if value in (None, "", "-"):
 return None
 return float(str(value).replace(",", "").strip())
 except (TypeError, ValueError):
<PARSED TEXT FOR PAGE: 5 / 56>
 return None
# ---------------------------------------------------------------- instrument master
def parse_master(text: str) -> dict[str, str]:
 """NSE cash-equity trading symbol -> Dhan security id. Series EQ only (intraday-eligible)."""
 ids: dict[str, str] = {}
 for row in csv.DictReader(io.StringIO(text)):
 exchange = _pick(row, "SEM_EXM_EXCH_ID", "EXCH_ID", "exchange").upper()
 segment = _pick(row, "SEM_SEGMENT", "SEGMENT").upper()
 symbol = _pick(row, "SEM_TRADING_SYMBOL", "TRADING_SYMBOL", "symbol")
 sec_id = _pick(row, "SEM_SMST_SECURITY_ID", "SEM_SECURITY_ID", "SECURITY_ID", "security_id")
 instrument = _pick(row, "SEM_INSTRUMENT_NAME", "INSTRUMENT", "instrument").upper()
 series = _pick(row, "SEM_SERIES", "SERIES").upper()
 if exchange != "NSE" or segment not in {"E", "EQUITY", "NSE_EQ"} or not symbol or not sec_id:
 continue
 if instrument and any(x in instrument for x in ("FUT", "OPT", "INDEX")):
 continue
 if series and series != "EQ": # BE / SM / ST ... are trade-for-trade or illiquid segments
 continue
 ids.setdefault(symbol, sec_id)
 return ids
def load_master(fetch: Fetch, *, now: datetime | None = None) -> tuple[dict[str, str], str]:
 """Return (ids, source). Uses the cache when fresh; falls back to a stale cache on fetch error."""
 now = now or now_utc()
 cached: dict = {}
 try:
 cached = json.loads(MASTER_CACHE.read_text(encoding="utf-8"))
 except (OSError, json.JSONDecodeError):
 cached = {}
 cached_ids = cached.get("ids") if isinstance(cached.get("ids"), dict) else {}
 try:
 generated = datetime.fromisoformat(str(cached.get("generated_at")).replace("Z", "+00:00"))
 fresh = now - generated < timedelta(hours=MASTER_MAX_AGE_HOURS)
 except (TypeError, ValueError):
 fresh = False
 if cached_ids and fresh:
 return cached_ids, "CACHE_FRESH"
 try:
 ids = parse_master(fetch(MASTER_URL).decode("utf-8-sig", errors="replace"))
 if len(ids) < 500: # a real NSE EQ list is ~2000+; refuse a truncated/garbled download
 raise RuntimeError(f"instrument master parsed to only {len(ids)} NSE EQ symbols")
 CACHE_DIR.mkdir(parents=True, exist_ok=True)
 tmp = MASTER_CACHE.with_name(MASTER_CACHE.name + ".tmp")
 tmp.write_text(json.dumps({"generated_at": iso(now), "ids": ids}, separators=(",", ":")), 
encoding="utf-8")
 os.replace(tmp, MASTER_CACHE)
 return ids, "FETCHED"
 except Exception as exc:
 if cached_ids:
 return cached_ids, f"CACHE_STALE ({exc})"
 raise
# ---------------------------------------------------------------- generic ranking
def _percentile_ranks(values: list[float | None]) -> list[float]:
 """0..1 percentile rank per item (None -> 0). Ties share the average rank."""
 indexed = sorted((v, i) for i, v in enumerate(values) if v is not None)
 ranks = [0.0] * len(values)
 n = len(indexed)
 if n == 0:
 return ranks
 pos = 0
 while pos < n:
 end = pos
 while end + 1 < n and indexed[end + 1][0] == indexed[pos][0]:
 end += 1
 avg = (pos + end) / 2 / max(n - 1, 1)
<PARSED TEXT FOR PAGE: 6 / 56>
 for k in range(pos, end + 1):
 ranks[indexed[k][1]] = avg
 pos = end + 1
 return ranks
def select_candidates(rows: list[dict], *, top_n: int = DEFAULT_TOP_N, max_price: float | None = None) -> 
tuple[list[dict], dict]:
 """Pick the shares worth deep analysis from the whole scanned market.
 Generic and symbol-agnostic. Eligible: affordable, price >= MIN_PRICE, change known.
 Liquidity floor: top half by turnover (price * volume) when volume is known.
 Score: 0.45 * turnover rank + 0.35 * momentum rank (signed % change) + 0.20 * range rank.
 """
 eligible = []
 for row in rows:
 price, change = _num(row.get("price")), _num(row.get("change"))
 if price is None or change is None or price < MIN_PRICE:
 continue
 if max_price is not None and price > max_price:
 continue
 volume = _num(row.get("volume"))
 high, low, prev = _num(row.get("high")), _num(row.get("low")), _num(row.get("prev_close"))
 eligible.append({
 "row": row, "change": change,
 "turnover": price * volume if volume and volume > 0 else None,
 "range": (high - low) / prev * 100 if None not in (high, low, prev) and prev else None,
 })
 stats = {"scanned": len(rows), "eligible": len(eligible), "liquid": 0, "selected": 0, "top_n": top_n,
 "max_price": max_price, "min_price": MIN_PRICE, "method": "turnover/momentum/range percentile 
rank"}
 if not eligible:
 return [], stats
 has_turnover = any(e["turnover"] is not None for e in eligible)
 t_rank = _percentile_ranks([e["turnover"] for e in eligible])
 m_rank = _percentile_ranks([e["change"] for e in eligible])
 r_rank = _percentile_ranks([e["range"] for e in eligible])
 scored = []
 for i, e in enumerate(eligible):
 if has_turnover and t_rank[i] < 0.5:
 continue
 score = 0.45 * t_rank[i] + 0.35 * m_rank[i] + 0.20 * r_rank[i] if has_turnover else 0.6 * m_rank[i] +
0.4 * r_rank[i]
 scored.append((score, str(e["row"].get("symbol")), e["row"]))
 stats["liquid"] = len(scored)
 scored.sort(key=lambda x: (-x[0], x[1]))
 selected = []
 for score, _, row in scored[:max(1, int(top_n))]:
 selected.append({**row, "selection_score": round(score, 4)})
 stats["selected"] = len(selected)
 return selected, stats
# ---------------------------------------------------------------- remembered selection
def save_selected(symbols: list[str], ids: dict[str, str], source: str, *, now: datetime | None = None) -> 
None:
 now = now or now_utc()
 CACHE_DIR.mkdir(parents=True, exist_ok=True)
 payload = {"generated_at": iso(now), "source": source, "symbols": symbols,
 "ids": {s: ids[s] for s in symbols if s in ids}}
 tmp = LAST_SELECTED.with_name(LAST_SELECTED.name + ".tmp")
 tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
 os.replace(tmp, LAST_SELECTED)
def load_carried(*, now: datetime | None = None) -> tuple[list[str], dict[str, str], str | None]:
 """The last market-discovered selection, if recent. (symbols, ids, generated_at)"""
 now = now or now_utc()
 try:
<PARSED TEXT FOR PAGE: 7 / 56>
 data = json.loads(LAST_SELECTED.read_text(encoding="utf-8"))
 generated = datetime.fromisoformat(str(data["generated_at"]).replace("Z", "+00:00"))
 if now - generated > timedelta(days=CARRY_MAX_AGE_DAYS):
 return [], {}, None
 symbols = [str(s) for s in data.get("symbols", []) if s]
 return symbols, {str(k): str(v) for k, v in (data.get("ids") or {}).items()}, 
str(data["generated_at"])
 except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError):
 return [], {}, None
# ---------------------------------------------------------------- bhavcopy bootstrap
def parse_bhavcopy(text: str) -> list[dict]:
 """NSE security-wise bhavcopy -> rows in the same shape the ranking expects."""
 rows = []
 reader = csv.DictReader(io.StringIO(text))
 for raw in reader:
 row = {str(k).strip().upper(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
 if row.get("SERIES") != "EQ":
 continue
 close, prev = _num(row.get("CLOSE_PRICE")), _num(row.get("PREV_CLOSE"))
 if close is None or not prev:
 continue
 rows.append({
 "symbol": row.get("SYMBOL"), "price": close, "prev_close": prev,
 "change": round((close - prev) / prev * 100, 2),
 "open": _num(row.get("OPEN_PRICE")), "high": _num(row.get("HIGH_PRICE")),
 "low": _num(row.get("LOW_PRICE")), "volume": _num(row.get("TTL_TRD_QNTY")),
 })
 return rows
def bhavcopy_universe(fetch: Fetch, *, top_n: int, max_price: float | None, today: datetime | None = None) ->
tuple[list[str], dict, str]:
 """Rank the previous trading session's whole market; returns (symbols, stats, session_date)."""
 today = today or now_utc()
 last_error = "no session tried"
 for back in range(1, 8):
 day = today - timedelta(days=back)
 if day.weekday() >= 5:
 continue
 url = BHAVCOPY_URL.format(ddmmyyyy=day.strftime("%d%m%Y"))
 try:
 rows = parse_bhavcopy(fetch(url).decode("utf-8-sig", errors="replace"))
 except Exception as exc: # holiday (404) / blocked / network
 last_error = str(exc)
 continue
 if len(rows) < 500:
 last_error = f"bhavcopy {day.date()} had only {len(rows)} EQ rows"
 continue
 selected, stats = select_candidates(rows, top_n=top_n, max_price=max_price)
 return [str(r["symbol"]) for r in selected], stats, day.strftime("%Y-%m-%d")
 raise RuntimeError(f"bhavcopy bootstrap unavailable: {last_error}")