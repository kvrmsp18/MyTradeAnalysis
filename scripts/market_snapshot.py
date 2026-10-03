#!/usr/bin/env python3
"""Collect truthful paper-trading market data from the WHOLE NSE equity market.
There is no hard-coded share list. See scripts/universe.py for the discovery design.
Source order
 1. Dhan /marketfeed/quote over every NSE EQ instrument (live full-market scan) -> generic ranking
 -> top N shares for deep analysis. Also records whole-market breadth (the regime).
 2. If Dhan is unavailable: the last market-discovered selection (<= 3 days old) is re-quoted via
 NSE India -> NSE proxy -> Yahoo Finance. If there is no such selection, the previous session's
 NSE bhavcopy bootstraps one.
 3. Otherwise DATA_UNAVAILABLE: the bot does not trade on a list nobody discovered.
Every row carries its own provider quote time (UTC). snapshot["data_as_of"] is the NEWEST provider
quote time, never "now", so the paper engine can tell a live feed from a frozen one (exchange
holiday / vendor stall). It is None when the provider gives no timestamp (freshness unverifiable).
"""
from __future__ import annotations
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import universe # noqa: E402
try: # the learning loop may widen/narrow the number of shares sent to deep analysis
 import learning_policy # noqa: E402
except Exception: # pragma: no cover - policy is optional
 learning_policy = None
MARKETFEED_URL = "https://api.dhan.co/v2/marketfeed/quote"
OUT = Path("public/data/market_snapshot.json")
YAHOO_INDICES = {"nifty50": "%5ENSEI", "banknifty": "%5ENSEBANK", "sensex": "%5EBSESN"}
NSE_HOME = "https://www.nseindia.com/"
NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol="
NSE_HEADERS = {
 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0.0.0 
Safari/537.36",
 "Accept": "application/json,text/plain,*/*",
 "Accept-Language": "en-US,en;q=0.9",
 "Referer": NSE_HOME,
}
BATCH = 1000 # Dhan allows up to 1000 instruments per market-quote request
REQUEST_GAP = 1.1 # ...and 1 request per second
MAX_CONSECUTIVE_FAILURES = 3
def utc_now() -> str:
 return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
def fetch(url: str, headers: dict | None = None, body: bytes | None = None, timeout: int = 25) -> bytes:
 req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST" if body else "GET")
 try:
 with urllib.request.urlopen(req, timeout=timeout) as response:
 return response.read()
 except urllib.error.HTTPError as exc:
 raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}") from exc
def analysis_budget() -> float:
<PARSED TEXT FOR PAGE: 9 / 56>
 return max(1000.0, float(os.getenv("PAPER_ANALYSIS_BUDGET", "1000") or 1000))
def top_n() -> int:
 if learning_policy is not None:
 try:
 return int(learning_policy.effective()["universe_top_n"])
 except Exception:
 pass
 return universe.DEFAULT_TOP_N
# ----------------------------------------------------------------- helpers
def _f(value: object) -> float | None:
 try:
 return None if value in (None, "") else float(value)
 except (TypeError, ValueError):
 return None
def _utc_iso_from_ist(ist: datetime) -> str:
 return (ist - timedelta(hours=5, minutes=30)).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", 
"Z")
def parse_dhan_time(value: object) -> str | None:
 if not value:
 return None
 for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
 try:
 return _utc_iso_from_ist(datetime.strptime(str(value).strip(), fmt))
 except ValueError:
 continue
 return None
def parse_nse_time(value: object) -> str | None:
 if not value:
 return None
 try:
 return _utc_iso_from_ist(datetime.strptime(str(value).strip(), "%d-%b-%Y %H:%M:%S"))
 except ValueError:
 return None
def latest_quote_time(rows: list[dict]) -> str | None:
 stamps = [r.get("quote_time") for r in rows if r.get("quote_time")]
 return max(stamps) if stamps else None
def derive_regime(rows: list[dict]) -> dict:
 changes = [c for c in (_f(r.get("change")) for r in rows) if c is not None]
 if not changes:
 return {"label": "UNAVAILABLE", "breadth": None, "confidence": 0, "observed": 0}
 breadth = sum(1 for c in changes if c > 0) / len(changes) * 100
 label = "BULLISH" if breadth >= 65 else "BEARISH" if breadth <= 35 else "MIXED"
 return {"label": label, "breadth": round(breadth, 1), "confidence": round(abs(breadth - 50) * 2, 1), 
"observed": len(changes)}
def yahoo_index_snapshot() -> dict:
 indices = {}
 for name, ticker in YAHOO_INDICES.items():
 try:
 url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
 payload = json.loads(fetch(url, {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, 
timeout=12).decode("utf-8"))
 meta = ((payload.get("chart", {}).get("result") or [None])[0] or {}).get("meta", {})
 price = meta.get("regularMarketPrice")
 previous = meta.get("previousClose", meta.get("chartPreviousClose"))
 if price is None:
<PARSED TEXT FOR PAGE: 10 / 56>
 continue
 change = (float(price) - float(previous)) / float(previous) * 100 if previous else None
 indices[name] = {"value": float(price), "change_pct": round(change, 2) if change is not None else
None}
 except Exception:
 continue
 return indices
def write_report(status: str, source: str, reason: object, stocks: list[dict], *, universe_info: dict,
 regime: dict | None = None, data_as_of: str | None = None) -> None:
 OUT.parent.mkdir(parents=True, exist_ok=True)
 provider_time = data_as_of if data_as_of is not None else latest_quote_time(stocks)
 # The paper executor treats a missing data_as_of as STALE and refuses to trade. If a provider
 # simply gives no (parseable) timestamp we fall back to the fetch time, and say so, rather than
 # silently disabling trading forever; with a provider timestamp the holiday/frozen-feed gate works.
 payload = {
 "status": status,
 "timestamp": utc_now(),
 "data_as_of": provider_time if provider_time else (utc_now() if stocks else None),
 "data_as_of_basis": "PROVIDER_QUOTE_TIME" if provider_time else ("FETCH_TIME_NO_PROVIDER_TIMESTAMP" 
if stocks else "NONE"),
 "source": source,
 "reason": reason,
 "paper_only": True,
 "universe": universe_info,
 "universe_count": universe_info.get("scanned", len(stocks)),
 "indices": yahoo_index_snapshot(),
 "regime": regime if regime is not None else derive_regime(stocks),
 "stocks": stocks,
 }
 tmp = OUT.with_name(OUT.name + ".tmp")
 tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
 os.replace(tmp, OUT)
# ----------------------------------------------------------------- Dhan: whole-market scan
def normalise_dhan(payload: dict, ids: dict[str, str]) -> list[dict]:
 data = payload.get("data", {}) if isinstance(payload, dict) else {}
 segment = data.get("NSE_EQ", data.get("NSE", {})) if isinstance(data, dict) else {}
 rows: list[dict] = []
 for symbol, sec_id in ids.items():
 quote = segment.get(str(sec_id)) if isinstance(segment, dict) else None
 if not isinstance(quote, dict):
 continue
 ltp = _f(quote.get("last_price", quote.get("ltp")))
 if ltp is None or ltp <= 0:
 continue
 ohlc = quote.get("ohlc") if isinstance(quote.get("ohlc"), dict) else {}
 close = _f(ohlc.get("close", quote.get("close"))) # previous session close
 change = _f(quote.get("change_percent"))
 if change is None and close:
 change = (ltp - close) / close * 100
 if change is None:
 net = _f(quote.get("net_change"))
 if net is not None and ltp - net:
 change = net / (ltp - net) * 100
 rows.append({
 "symbol": symbol, "price": ltp,
 "change": round(change, 2) if change is not None else None, # unknown stays None, never 0
 "open": _f(ohlc.get("open", quote.get("open"))),
 "high": _f(ohlc.get("high", quote.get("high"))),
 "low": _f(ohlc.get("low", quote.get("low"))),
 "prev_close": close, "volume": quote.get("volume"),
 "quote_time": parse_dhan_time(quote.get("last_trade_time")),
 "security_id": str(sec_id),
 })
 return rows
def dhan_scan(ids: dict[str, str], token: str, client_id: str) -> list[dict]:
<PARSED TEXT FOR PAGE: 11 / 56>
 headers = {"access-token": token, "client-id": client_id, "Content-Type": "application/json", "Accept": 
"application/json"}
 items = list(ids.items())
 rows: list[dict] = []
 errors: list[str] = []
 for start in range(0, len(items), BATCH):
 batch = dict(items[start:start + BATCH])
 if start:
 time.sleep(REQUEST_GAP)
 try:
 body = json.dumps({"NSE_EQ": [int(v) for v in batch.values()]}).encode()
 rows.extend(normalise_dhan(json.loads(fetch(MARKETFEED_URL, headers, body).decode("utf-8")), 
batch))
 except Exception as exc:
 errors.append(str(exc))
 if not rows:
 raise RuntimeError("Dhan returned no usable NSE equity quotes" + (f": {errors[0]}" if errors else 
"."))
 return rows
# ----------------------------------------------------------------- fallbacks on a discovered list
def nse_session():
 import http.cookiejar
 opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 opener.open(urllib.request.Request(NSE_HOME, headers=NSE_HEADERS), timeout=20).read()
 return opener
def _nse_row(symbol: str, data: dict) -> dict:
 info = data.get("priceInfo", {})
 price = info.get("lastPrice")
 if price is None:
 raise RuntimeError("NSE quote missing lastPrice")
 return {
 "symbol": symbol, "price": float(price),
 "change": float(info["pChange"]) if info.get("pChange") is not None else None,
 "open": info.get("open"), "high": info.get("intraDayHighLow", {}).get("max"),
 "low": info.get("intraDayHighLow", {}).get("min"), "prev_close": info.get("previousClose"),
 "volume": data.get("marketDeptOrderBook", {}).get("tradeInfo", {}).get("totalTradedVolume"),
 "quote_time": parse_nse_time((data.get("metadata") or {}).get("lastUpdateTime")),
 "security_id": None,
 }
def nse_quote(opener, symbol: str) -> dict:
 request = urllib.request.Request(NSE_QUOTE_URL + urllib.parse.quote(symbol), headers=NSE_HEADERS)
 with opener.open(request, timeout=20) as response:
 return _nse_row(symbol, json.loads(response.read().decode("utf-8")))
def nse_proxy_quote(symbol: str) -> dict:
 request = urllib.request.Request("https://r.jina.ai/" + NSE_QUOTE_URL + urllib.parse.quote(symbol),
 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
 with urllib.request.urlopen(request, timeout=30) as response:
 return _nse_row(symbol, json.loads(response.read().decode("utf-8", "replace")))
def _serial(symbols: list[str], quote_fn, label: str) -> tuple[list[dict], list[str]]:
 rows: list[dict] = []
 errors: list[str] = []
 streak = 0
 for symbol in symbols:
 try:
 rows.append(quote_fn(symbol))
 streak = 0
 except Exception as exc:
 errors.append(f"{symbol}: {exc}")
 streak += 1
 if "HTTP 403" in str(exc):
 raise RuntimeError(f"{label} access blocked (HTTP 403); stopping fallback early.")
<PARSED TEXT FOR PAGE: 12 / 56>
 if not rows and streak >= MAX_CONSECUTIVE_FAILURES:
 raise RuntimeError(f"{label} fallback failed: " + "; ".join(errors[:5]))
 if not rows:
 raise RuntimeError(f"{label} fallback failed: " + "; ".join(errors[:10]))
 return rows, errors
def nse_fallback(symbols: list[str]) -> tuple[list[dict], list[str]]:
 opener = nse_session()
 return _serial(symbols, lambda s: nse_quote(opener, s), "NSE India")
def nse_proxy_fallback(symbols: list[str]) -> tuple[list[dict], list[str]]:
 return _serial(symbols, nse_proxy_quote, "NSE proxy")
def yahoo_quote(symbol: str) -> dict:
 ticker = urllib.parse.quote(symbol + ".NS", safe="")
 url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?
interval=5m&range=1d&events=div%2Csplits"
 payload = json.loads(fetch(url, {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, 
timeout=12).decode("utf-8"))
 result = payload.get("chart", {}).get("result") or []
 if not result:
 raise RuntimeError("Yahoo returned no chart")
 meta = result[0].get("meta", {})
 price = meta.get("regularMarketPrice")
 close = meta.get("previousClose", meta.get("chartPreviousClose"))
 if price is None:
 raise RuntimeError("Yahoo price unavailable")
 change = (float(price) - float(close)) / float(close) * 100 if close else None
 stamp = meta.get("regularMarketTime")
 quote_time = (datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
 if isinstance(stamp, (int, float)) and stamp > 0 else None)
 return {
 "symbol": symbol, "price": float(price), "change": round(change, 2) if change is not None else None,
 "open": meta.get("regularMarketDayOpen"), "high": meta.get("regularMarketDayHigh"),
 "low": meta.get("regularMarketDayLow"), "prev_close": close,
 "volume": meta.get("regularMarketVolume"), "quote_time": quote_time, "security_id": None,
 }
def yahoo_fallback(symbols: list[str]) -> tuple[list[dict], list[str]]:
 rows: list[dict] = []
 errors: list[str] = []
 with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
 futures = {pool.submit(yahoo_quote, s): s for s in symbols}
 for future in concurrent.futures.as_completed(futures):
 try:
 rows.append(future.result())
 except Exception as exc:
 errors.append(f"{futures[future]}: {exc}")
 rows.sort(key=lambda r: r["symbol"])
 if not rows:
 raise RuntimeError("Yahoo fallback failed: " + "; ".join(errors[:10]))
 return rows, errors
# ----------------------------------------------------------------- main
def main() -> int:
 client_id = (os.getenv("DHAN_CLIENT_ID") or "").strip()
 token = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
 budget, n = analysis_budget(), top_n()
 dhan_error: str | None = None
 if client_id and token:
 try:
 ids, master_source = universe.load_master(fetch)
 all_rows = dhan_scan(ids, token, client_id)
 selected, stats = universe.select_candidates(all_rows, top_n=n, max_price=budget)
 if selected:
<PARSED TEXT FOR PAGE: 13 / 56>
 universe.save_selected([r["symbol"] for r in selected], ids, "DHAN_FULL_MARKET_SCAN")
 info = {"mode": "DYNAMIC_FULL_NSE_SCAN", "master_source": master_source, "instruments": 
len(ids), **stats}
 write_report("LIVE_MARKET_DATA", "Dhan market feed (full NSE equity scan)",
 {"credential": "DHAN_ACCESS_TOKEN"}, selected, universe_info=info,
 regime=derive_regime(all_rows), data_as_of=latest_quote_time(all_rows))
 print(f"Dhan scan: {stats['scanned']} quoted, {stats['eligible']} eligible, 
{stats['selected']} selected.")
 return 0
 dhan_error = f"Dhan scan produced no eligible shares ({stats})."
 except Exception as exc:
 dhan_error = str(exc)
 else:
 dhan_error = "DHAN_CLIENT_ID is not configured." if not client_id else "DHAN_ACCESS_TOKEN is not 
configured."
 # Dhan unavailable -> fall back on the last list the live market itself produced.
 symbols, _, discovered_at = universe.load_carried()
 info = {"mode": "CARRIED_DYNAMIC", "discovered_at": discovered_at, "scanned": len(symbols)}
 if not symbols:
 try:
 symbols, stats, session = universe.bhavcopy_universe(fetch, top_n=n, max_price=budget)
 universe.save_selected(symbols, {}, f"NSE_BHAVCOPY_{session}")
 info = {"mode": "BHAVCOPY_PREVIOUS_SESSION", "session": session, **stats}
 except Exception as exc:
 write_report("DATA_UNAVAILABLE", "none",
 {"dhan_error": dhan_error, "universe_error": str(exc),
 "note": "No discovered universe: refusing to trade a hand-typed list."},
 [], universe_info={"mode": "NONE", "scanned": 0})
 print(f"Market data unavailable: Dhan={dhan_error}; universe={exc}", file=sys.stderr)
 return 0
 chain = (
 ("LIVE_MARKET_DATA_NSE", "NSE India public quote feed", nse_fallback),
 ("LIVE_MARKET_DATA_NSE_PROXY", "NSE India via public fetch proxy", nse_proxy_fallback),
 ("LIVE_MARKET_DATA_FALLBACK", "Yahoo Finance chart feed", yahoo_fallback),
 )
 failures: dict[str, str] = {}
 for status, source, fn in chain:
 try:
 rows, errors = fn(symbols)
 write_report(status, source, {"dhan_error": dhan_error, "earlier_failures": failures, 
"fallback_errors": errors[:20]},
 rows, universe_info={**info, "selected": len(rows)})
 print(f"Using {source} on the {info['mode']} list because Dhan was unavailable: {dhan_error}")
 return 0
 except Exception as exc:
 failures[status] = str(exc)
 write_report("DATA_UNAVAILABLE", "none", {"dhan_error": dhan_error, **failures}, [], universe_info=info)
 print(f"Market data unavailable: Dhan={dhan_error}; {failures}", file=sys.stderr)
 return 0
if __name__ == "__main__":
 raise SystemExit(main())