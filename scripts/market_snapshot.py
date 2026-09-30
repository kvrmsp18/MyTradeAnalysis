#!/usr/bin/env python3
"""Collect truthful paper-trading market data.

Primary source: Dhan marketfeed.
Fallback order: NSE India -> NSE proxy -> Yahoo Finance.

The fallback is real market data but is explicitly labelled. It is never
presented as Dhan data and never used for broker orders.

The initial paper-validation universe is a broad Nifty-50 style liquid basket,
not a stock-specific watchlist. When Dhan marketfeed is available, the same
basket is resolved from Dhan's instrument master.
"""
from __future__ import annotations

import concurrent.futures
import csv
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
MARKETFEED_URL = "https://api.dhan.co/v2/marketfeed/ltp"
OUT = Path("public/data/market_snapshot.json")

# Validation universe only. It is deliberately broad and sector-diverse.
# It is not a permanent stock preference and can be replaced by a dynamic
# exchange-universe loader when the Dhan data subscription is available.
SYMBOLS = [
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK",
    "BAJAJ-AUTO","BAJFINANCE","BAJAJFINSV","BEL","BHARTIARTL",
    "CIPLA","COALINDIA","DRREDDY","EICHERMOT","ETERNAL",
    "GRASIM","HCLTECH","HDFCBANK","HDFCLIFE","HEROMOTOCO",
    "HINDALCO","HINDUNILVR","ICICIBANK","INDUSINDBK","INFY",
    "ITC","JIOFIN","JSWSTEEL","KOTAKBANK","LT",
    "M&M","MARUTI","MAXHEALTH","NESTLEIND","NTPC",
    "ONGC","POWERGRID","RELIANCE","SBILIFE","SBIN",
    "SHRIRAMFIN","SUNPHARMA","TATACONSUM","TATAMOTORS","TATASTEEL",
    "TCS","TECHM","TITAN","TRENT","ULTRACEMCO","WIPRO",
]

YAHOO = {symbol: symbol.replace("&", "%26") + ".NS" for symbol in SYMBOLS}
YAHOO["M&M"] = "M%26M.NS"
YAHOO_INDICES = {"nifty50":"%5ENSEI", "banknifty":"%5ENSEBANK", "sensex":"%5EBSESN"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def yahoo_index_snapshot() -> dict:
    indices = {}
    for name, ticker in YAHOO_INDICES.items():
        try:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                "?interval=5m&range=1d"
            )
            payload = json.loads(
                fetch(url, {"User-Agent":"Mozilla/5.0","Accept":"application/json"}, timeout=12).decode("utf-8")
            )
            result = (payload.get("chart", {}).get("result") or [None])[0]
            meta = (result or {}).get("meta", {})
            price = meta.get("regularMarketPrice")
            previous = meta.get("previousClose", meta.get("chartPreviousClose"))
            if price is None:
                continue
            change = ((float(price)-float(previous))/float(previous)*100) if previous else None
            indices[name] = {"value":float(price),"change_pct":round(change,2) if change is not None else None}
        except Exception:
            continue
    return indices


def write_report(status: str, source: str, reason: object, stocks: list[dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "status": status,
                "timestamp": utc_now(),
                "source": source,
                "reason": reason,
                "paper_only": True,
                "universe": "NIFTY50_VALIDATION_BASKET",
                "universe_count": len(SYMBOLS),
                "indices": yahoo_index_snapshot(),
                "stocks": stocks,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def fetch(url: str, headers: dict | None = None, body: bytes | None = None, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        data=body,
        headers=headers or {},
        method="POST" if body else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {body_text[:500]}") from exc


def pick(row: dict, *names: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def resolve_ids() -> dict[str, str]:
    text = fetch(MASTER_URL).decode("utf-8-sig", errors="replace")
    result: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        exchange = pick(row, "SEM_EXM_EXCH_ID", "EXCH_ID", "exchange")
        segment = pick(row, "SEM_SEGMENT", "SEGMENT")
        symbol = pick(row, "SEM_TRADING_SYMBOL", "TRADING_SYMBOL", "symbol")
        sec_id = pick(row, "SEM_SMST_SECURITY_ID", "SEM_SECURITY_ID", "SECURITY_ID", "security_id")
        if (
            exchange.upper() == "NSE"
            and segment.upper() in ("E", "EQUITY", "NSE_EQ")
            and symbol in SYMBOLS
            and sec_id
        ):
            result[symbol] = sec_id

    missing = [symbol for symbol in SYMBOLS if symbol not in result]
    if missing:
        raise RuntimeError(f"Instrument IDs unavailable for: {', '.join(missing[:15])}")
    return result


def normalise_dhan(payload: dict, ids: dict[str, str]) -> list[dict]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    segment = data.get("NSE_EQ", data.get("NSE", {})) if isinstance(data, dict) else {}
    rows: list[dict] = []

    for symbol, sec_id in ids.items():
        quote = segment.get(str(sec_id)) if isinstance(segment, dict) else None
        if not isinstance(quote, dict):
            continue

        ltp = quote.get("last_price", quote.get("ltp"))
        close = quote.get("close")
        if ltp is None:
            continue

        change = quote.get("change_percent")
        if change is None and close not in (None, 0):
            change = (float(ltp) - float(close)) / float(close) * 100

        rows.append(
            {
                "symbol": symbol,
                "price": float(ltp),
                "change": round(float(change or 0), 2),
                "open": quote.get("open"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "prev_close": close,
                "volume": quote.get("volume"),
                "security_id": str(sec_id),
            }
        )
    return rows


NSE_HOME = "https://www.nseindia.com/"
NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol="
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
}


def nse_session():
    import http.cookiejar
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.open(urllib.request.Request(NSE_HOME, headers=NSE_HEADERS), timeout=20).read()
    return opener


def nse_quote(opener, symbol: str) -> dict:
    request = urllib.request.Request(
        NSE_QUOTE_URL + urllib.parse.quote(symbol),
        headers=NSE_HEADERS,
    )
    with opener.open(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))

    price_info = data.get("priceInfo", {})
    price = price_info.get("lastPrice")
    if price is None:
        raise RuntimeError("NSE quote missing lastPrice")

    return {
        "symbol": symbol,
        "price": float(price),
        "change": float(price_info.get("pChange") or 0),
        "open": price_info.get("open"),
        "high": price_info.get("intraDayHighLow", {}).get("max"),
        "low": price_info.get("intraDayHighLow", {}).get("min"),
        "prev_close": price_info.get("previousClose"),
        "volume": data.get("marketDeptOrderBook", {}).get("tradeInfo", {}).get("totalTradedVolume"),
        "security_id": None,
    }


def nse_proxy_quote(symbol: str) -> dict:
    target = "https://www.nseindia.com/api/quote-equity?symbol=" + urllib.parse.quote(symbol)
    proxy = "https://r.jina.ai/" + target
    request = urllib.request.Request(
        proxy,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))

    price_info = data.get("priceInfo", {})
    price = price_info.get("lastPrice")
    if price is None:
        raise RuntimeError("NSE proxy quote missing lastPrice")

    return {
        "symbol": symbol,
        "price": float(price),
        "change": float(price_info.get("pChange") or 0),
        "open": price_info.get("open"),
        "high": price_info.get("intraDayHighLow", {}).get("max"),
        "low": price_info.get("intraDayHighLow", {}).get("min"),
        "prev_close": price_info.get("previousClose"),
        "volume": data.get("marketDeptOrderBook", {}).get("tradeInfo", {}).get("totalTradedVolume"),
        "security_id": None,
    }


def nse_fallback() -> tuple[list[dict], list[str]]:
    opener = nse_session()
    rows: list[dict] = []
    errors: list[str] = []
    for symbol in SYMBOLS:
        try:
            rows.append(nse_quote(opener, symbol))
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
    if not rows:
        raise RuntimeError("NSE India fallback failed: " + "; ".join(errors[:10]))
    return rows, errors


def nse_proxy_fallback() -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    for symbol in SYMBOLS:
        try:
            rows.append(nse_proxy_quote(symbol))
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
    if not rows:
        raise RuntimeError("NSE proxy fallback failed: " + "; ".join(errors[:10]))
    return rows, errors


def yahoo_quote(symbol: str) -> dict:
    ticker = urllib.parse.quote(YAHOO[symbol], safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        "?interval=5m&range=1d&events=div%2Csplits"
    )
    payload = json.loads(
        fetch(
            url,
            {"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=12,
        ).decode("utf-8")
    )
    result = payload.get("chart", {}).get("result") or []
    if not result:
        raise RuntimeError("Yahoo returned no chart")

    meta = result[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    close = meta.get("previousClose", meta.get("chartPreviousClose"))
    if price is None:
        raise RuntimeError("Yahoo price unavailable")

    change = (float(price) - float(close)) / float(close) * 100 if close else 0
    return {
        "symbol": symbol,
        "price": float(price),
        "change": round(change, 2),
        "open": meta.get("regularMarketDayOpen"),
        "high": meta.get("regularMarketDayHigh"),
        "low": meta.get("regularMarketDayLow"),
        "prev_close": close,
        "volume": meta.get("regularMarketVolume"),
        "security_id": None,
    }


def yahoo_fallback() -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []

    # Parallel fetch keeps the paper-cycle within the GitHub Actions time budget.
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(yahoo_quote, symbol): symbol for symbol in SYMBOLS}
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")

    rows.sort(key=lambda row: row["symbol"])
    if not rows:
        raise RuntimeError("Yahoo fallback failed: " + "; ".join(errors[:10]))
    return rows, errors


def main() -> int:
    client_id = ""
    token = ""
    try:
        import os
        client_id = (os.getenv("DHAN_CLIENT_ID") or "").strip()
        token = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
    except Exception:
        pass

    dhan_error: str | None = None
    nse_exc: Exception | None = None
    nse_proxy_exc: Exception | None = None

    if client_id and token:
        try:
            ids = resolve_ids()
            body = json.dumps({"NSE_EQ": [int(value) for value in ids.values()]}).encode()
            payload = json.loads(
                fetch(
                    MARKETFEED_URL,
                    {
                        "access-token": token,
                        "client-id": client_id,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    body,
                ).decode("utf-8")
            )
            rows = normalise_dhan(payload, ids)
            if rows:
                write_report(
                    "LIVE_MARKET_DATA",
                    "Dhan market feed",
                    {"credential": "DHAN_ACCESS_TOKEN", "universe": "NIFTY50_VALIDATION_BASKET"},
                    rows,
                )
                return 0
            dhan_error = "Dhan returned no usable NSE equity quotes."
        except Exception as exc:
            dhan_error = str(exc)
    elif not client_id:
        dhan_error = "DHAN_CLIENT_ID is not configured."
    else:
        dhan_error = "DHAN_ACCESS_TOKEN is not configured."

    try:
        rows, errors = nse_fallback()
        write_report(
            "LIVE_MARKET_DATA_NSE",
            "NSE India public quote feed",
            {"dhan_error": dhan_error, "fallback_errors": errors},
            rows,
        )
        print(f"Using NSE India because Dhan was unavailable: {dhan_error}")
        return 0
    except Exception as exc:
        nse_exc = exc

    try:
        rows, errors = nse_proxy_fallback()
        write_report(
            "LIVE_MARKET_DATA_NSE_PROXY",
            "NSE India via public fetch proxy",
            {"dhan_error": dhan_error, "direct_nse_error": str(nse_exc), "fallback_errors": errors},
            rows,
        )
        print(f"Using NSE India via proxy because direct NSE access was unavailable: {nse_exc}")
        return 0
    except Exception as exc:
        nse_proxy_exc = exc

    try:
        rows, errors = yahoo_fallback()
        write_report(
            "LIVE_MARKET_DATA_FALLBACK",
            "Yahoo Finance chart feed",
            {
                "dhan_error": dhan_error,
                "nse_error": str(nse_exc),
                "nse_proxy_error": str(nse_proxy_exc),
                "fallback_errors": errors,
            },
            rows,
        )
        print(
            "Using Yahoo fallback because Dhan and NSE were unavailable: "
            f"Dhan={dhan_error}; NSE={nse_exc}; proxy={nse_proxy_exc}; "
            f"received={len(rows)}/{len(SYMBOLS)}"
        )
        return 0
    except Exception as exc:
        write_report(
            "DATA_UNAVAILABLE",
            "none",
            {
                "dhan_error": dhan_error,
                "nse_error": str(nse_exc),
                "nse_proxy_error": str(nse_proxy_exc),
                "fallback_error": str(exc),
            },
            [],
        )
        print(
            "Market data unavailable: "
            f"Dhan={dhan_error}; NSE={nse_exc}; proxy={nse_proxy_exc}; fallback={exc}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
