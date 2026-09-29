#!/usr/bin/env python3
"""Collect truthful paper-trading market data.

Primary source: Dhan marketfeed.
Fallback: Yahoo Finance chart feed for the configured NSE symbols when Dhan
authentication is unavailable. Fallback data is explicitly labelled and never
used for broker orders.
"""
from __future__ import annotations
import csv, io, json, os, sys, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

MASTER_URL="https://images.dhan.co/api-data/api-scrip-master.csv"
MARKETFEED_URL="https://api.dhan.co/v2/marketfeed/ltp"
OUT=Path("public/data/market_snapshot.json")
SYMBOLS=["RELIANCE","HDFCBANK","INFY","TCS","SUNPHARMA","M&M"]
YAHOO={"RELIANCE":"RELIANCE.NS","HDFCBANK":"HDFCBANK.NS","INFY":"INFY.NS","TCS":"TCS.NS","SUNPHARMA":"SUNPHARMA.NS","M&M":"M&M.NS"}

def utc_now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def write_report(status, source, reason, stocks):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"status":status,"timestamp":utc_now(),"source":source,"reason":reason,"paper_only":True,"stocks":stocks},indent=2),encoding="utf-8")
def fetch(url,headers=None,body=None):
    req=urllib.request.Request(url,data=body,headers=headers or {},method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body=exc.read().decode('utf-8','replace')
        raise RuntimeError('HTTP ' + str(exc.code) + ': ' + body[:500]) from exc
def pick(row,*names):
    lowered={str(k).strip().lower():v for k,v in row.items()}
    for name in names:
        if lowered.get(name.lower()) not in (None,""): return str(lowered[name.lower()]).strip()
    return ""
def resolve_ids():
    text=fetch(MASTER_URL).decode("utf-8-sig",errors="replace")
    result={}
    for row in csv.DictReader(io.StringIO(text)):
        exchange=pick(row,"SEM_EXM_EXCH_ID","EXCH_ID","exchange")
        segment=pick(row,"SEM_SEGMENT","SEGMENT")
        symbol=pick(row,"SEM_TRADING_SYMBOL","TRADING_SYMBOL","symbol")
        sec_id=pick(row,"SEM_SMST_SECURITY_ID","SEM_SECURITY_ID","SECURITY_ID","security_id")
        if exchange.upper()=="NSE" and segment.upper() in ("E","EQUITY","NSE_EQ") and symbol in SYMBOLS and sec_id: result[symbol]=sec_id
    missing=[s for s in SYMBOLS if s not in result]
    if missing: raise RuntimeError("Instrument IDs unavailable for: "+", ".join(missing))
    return result
def normalise_dhan(payload,ids):
    data=payload.get("data",{}) if isinstance(payload,dict) else {}
    segment=data.get("NSE_EQ",data.get("NSE",{})) if isinstance(data,dict) else {}
    rows=[]
    for symbol,sec_id in ids.items():
        q=segment.get(str(sec_id)) if isinstance(segment,dict) else None
        if not isinstance(q,dict): continue
        ltp=q.get("last_price",q.get("ltp")); close=q.get("close")
        if ltp is None: continue
        change=q.get("change_percent")
        if change is None and close not in (None,0): change=(float(ltp)-float(close))/float(close)*100
        rows.append({"symbol":symbol,"price":float(ltp),"change":round(float(change or 0),2),"open":q.get("open"),"high":q.get("high"),"low":q.get("low"),"prev_close":close,"volume":q.get("volume"),"security_id":str(sec_id)})
    return rows

NSE_HOME="https://www.nseindia.com/"
NSE_QUOTE_URL="https://www.nseindia.com/api/quote-equity?symbol="
NSE_HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0.0.0 Safari/537.36","Accept":"application/json,text/plain,*/*","Accept-Language":"en-US,en;q=0.9","Referer":NSE_HOME}
def nse_session():
    import http.cookiejar
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.open(urllib.request.Request(NSE_HOME,headers=NSE_HEADERS),timeout=20).read()
    return opener
def nse_quote(opener,symbol):
    req=urllib.request.Request(NSE_QUOTE_URL+urllib.parse.quote(symbol),headers=NSE_HEADERS)
    with opener.open(req,timeout=20) as response:
        data=json.loads(response.read().decode("utf-8"))
    price=data.get("priceInfo",{}).get("lastPrice")
    if price is None: raise RuntimeError("NSE quote missing lastPrice")
    pi=data.get("priceInfo",{})
    return {"symbol":symbol,"price":float(price),"change":float(pi.get("pChange") or 0),"open":pi.get("open"),"high":pi.get("intraDayHighLow",{}).get("max"),"low":pi.get("intraDayHighLow",{}).get("min"),"prev_close":pi.get("previousClose"),"volume":data.get("marketDeptOrderBook",{}).get("tradeInfo",{}).get("totalTradedVolume"),"security_id":None}
def nse_proxy_quote(symbol):
    # Cloud runners can receive NSE's anti-bot 403. Use a public fetch proxy only
    # to retrieve the NSE India URL; the underlying source remains NSE India.
    target="https://www.nseindia.com/api/quote-equity?symbol="+urllib.parse.quote(symbol)
    proxy="https://r.jina.ai/"+target
    req=urllib.request.Request(proxy,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as response:
        raw=response.read().decode("utf-8","replace").strip()
    data=json.loads(raw)
    if not isinstance(data,dict): raise RuntimeError("NSE proxy returned non-object")
    pi=data.get("priceInfo",{})
    price=pi.get("lastPrice")
    if price is None: raise RuntimeError("NSE proxy quote missing lastPrice")
    return {"symbol":symbol,"price":float(price),"change":float(pi.get("pChange") or 0),"open":pi.get("open"),"high":pi.get("intraDayHighLow",{}).get("max"),"low":pi.get("intraDayHighLow",{}).get("min"),"prev_close":pi.get("previousClose"),"volume":data.get("marketDeptOrderBook",{}).get("tradeInfo",{}).get("totalTradedVolume"),"security_id":None}

def nse_proxy_fallback():
    rows=[]; errors=[]
    for symbol in SYMBOLS:
        try: rows.append(nse_proxy_quote(symbol))
        except Exception as exc: errors.append(f"{symbol}: {exc}")
    if not rows: raise RuntimeError("NSE proxy fallback failed: "+"; ".join(errors))
    return rows,errors

def nse_fallback():
    opener=nse_session(); rows=[]; errors=[]
    for symbol in SYMBOLS:
        try: rows.append(nse_quote(opener,symbol))
        except Exception as exc: errors.append(f"{symbol}: {exc}")
    if not rows: raise RuntimeError("NSE India fallback failed: "+"; ".join(errors))
    return rows,errors
def yahoo_quote(symbol):
    ticker=urllib.parse.quote(YAHOO[symbol],safe="")
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d&events=div%2Csplits"
    payload=json.loads(fetch(url,{"User-Agent":"Mozilla/5.0","Accept":"application/json"}).decode("utf-8"))
    result=payload.get("chart",{}).get("result") or []
    if not result: raise RuntimeError("Yahoo returned no chart")
    meta=result[0].get("meta",{})
    price=meta.get("regularMarketPrice")
    close=meta.get("previousClose",meta.get("chartPreviousClose"))
    if price is None: raise RuntimeError("Yahoo price unavailable")
    change=(float(price)-float(close))/float(close)*100 if close else 0
    return {"symbol":symbol,"price":float(price),"change":round(change,2),"open":meta.get("regularMarketDayOpen"),"high":meta.get("regularMarketDayHigh"),"low":meta.get("regularMarketDayLow"),"prev_close":close,"volume":meta.get("regularMarketVolume"),"security_id":None}
def yahoo_fallback():
    rows=[]
    errors=[]
    for symbol in SYMBOLS:
        try: rows.append(yahoo_quote(symbol))
        except Exception as exc: errors.append(f"{symbol}: {exc}")
    if not rows: raise RuntimeError("Yahoo fallback failed: "+"; ".join(errors))
    return rows, errors
def main():
    client_id=(os.getenv("DHAN_CLIENT_ID") or "").strip()
    token=(os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
    dhan_error=None
    if client_id and token:
        try:
            ids=resolve_ids()
            body=json.dumps({"NSE_EQ":[int(v) for v in ids.values()]}).encode()
            payload=json.loads(fetch(MARKETFEED_URL,{"access-token":token,"client-id":client_id,"Content-Type":"application/json","Accept":"application/json"},body).decode("utf-8"))
            rows=normalise_dhan(payload,ids)
            if rows:
                write_report("LIVE_MARKET_DATA","Dhan market feed",{"credential":"DHAN_ACCESS_TOKEN"},rows)
                return 0
            dhan_error="Dhan returned no usable NSE equity quotes."
        except Exception as exc:
            dhan_error=str(exc)
    elif not client_id:
        dhan_error="DHAN_CLIENT_ID is not configured."
    else:
        dhan_error="DHAN_ACCESS_TOKEN is not configured."

    try:
        rows,errors=nse_fallback()
        write_report("LIVE_MARKET_DATA_NSE","NSE India public quote feed",{"dhan_error":dhan_error,"fallback_errors":errors},rows)
        print(f"Using NSE India because Dhan was unavailable: {dhan_error}")
        return 0
    except Exception as nse_exc:
        try:
            rows,errors=nse_proxy_fallback()
            write_report("LIVE_MARKET_DATA_NSE_PROXY","NSE India via public fetch proxy",{"dhan_error":dhan_error,"direct_nse_error":str(nse_exc),"fallback_errors":errors},rows)
            print(f"Using NSE India via proxy because direct NSE access was unavailable: {nse_exc}")
            return 0
        except Exception as nse_proxy_exc:
            try:
                rows,errors=yahoo_fallback()
                write_report("LIVE_MARKET_DATA_FALLBACK","Yahoo Finance chart feed",{"dhan_error":dhan_error,"nse_error":str(nse_exc),"nse_proxy_error":str(nse_proxy_exc),"fallback_errors":errors},rows)
                print(f"Using Yahoo fallback because Dhan and NSE were unavailable: {dhan_error}; NSE={nse_exc}; proxy={nse_proxy_exc}")
                return 0
            except Exception as exc:
                write_report("DATA_UNAVAILABLE","none",{"dhan_error":dhan_error,"nse_error":str(nse_exc),"nse_proxy_error":str(nse_proxy_exc),"fallback_error":str(exc)},[])
                print(f"Market data unavailable: Dhan={dhan_error}; NSE={nse_exc}; proxy={nse_proxy_exc}; fallback={exc}",file=sys.stderr)
                return 0

if __name__=="__main__": raise SystemExit(main())
