#!/usr/bin/env python3
"""Truthful paper-only market snapshot using a dynamic full NSE equity universe."""
from __future__ import annotations
import concurrent.futures,csv,json,os,sys,time,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import universe
from universe import load_master,save_selected,load_carried,bhavcopy_universe

MARKETFEED_URL="https://api.dhan.co/v2/marketfeed/quote"
OUT=Path("public/data/market_snapshot.json")
BATCH=1000
TOP_N=int(os.getenv("UNIVERSE_TOP_N","60") or 60)
BUDGET=max(1000.0,float(os.getenv("PAPER_ANALYSIS_BUDGET","1000") or 1000))
NSE_HOME="https://www.nseindia.com/"
NSE_QUOTE_URL="https://www.nseindia.com/api/quote-equity?symbol="
NSE_HEADERS={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/plain,*/*","Accept-Language":"en-US,en;q=0.9","Referer":NSE_HOME}

def utc_now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def fetch(url,headers=None,body=None,timeout=25):
    req=urllib.request.Request(url,data=body,headers=headers or {},method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()
    except urllib.error.HTTPError as e: raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:500]}") from e

def parse_time(v):
    if v in (None,""): return None
    s=str(v).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S","%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S"):
        try:
            dt=datetime.strptime(s,fmt)
            if dt.tzinfo is None: dt=dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
        except ValueError: pass
    try:return datetime.fromtimestamp(float(v),tz=timezone.utc).isoformat().replace("+00:00","Z")
    except (TypeError,ValueError):return None

def normalise_dhan(payload,ids):
    data=payload.get("data",{}) if isinstance(payload,dict) else {}
    seg=data.get("NSE_EQ",data.get("NSE",{})) if isinstance(data,dict) else {}
    rows=[]
    for symbol,sec in ids.items():
        q=seg.get(str(sec)) if isinstance(seg,dict) else None
        if not isinstance(q,dict):continue
        ltp=q.get("last_price",q.get("ltp")); o=q.get("ohlc") if isinstance(q.get("ohlc"),dict) else {}
        prev=o.get("close",q.get("close"))
        if ltp is None:continue
        change=q.get("change_percent")
        if change is None and prev not in (None,0):
            change=(float(ltp)-float(prev))/float(prev)*100
        qt=parse_time(q.get("last_trade_time") or q.get("last_traded_time") or q.get("quote_time"))
        rows.append({"symbol":symbol,"price":float(ltp),"change":round(float(change),2) if change is not None else None,
                     "open":o.get("open",q.get("open")),"high":o.get("high",q.get("high")),"low":o.get("low",q.get("low")),
                     "prev_close":prev,"volume":q.get("volume"),"security_id":str(sec),"quote_time":qt})
    return rows

def derive_regime(stocks):
    changes=[float(x["change"]) for x in stocks if x.get("change") is not None]
    if not changes:return {"observed":len(stocks),"label":"UNAVAILABLE","breadth":None,"confidence":0}
    breadth=sum(x>0 for x in changes)/len(changes)*100
    label="BULLISH" if breadth>=65 else "BEARISH" if breadth<=35 else "MIXED"
    return {"observed":len(stocks),"label":label,"breadth":round(breadth,1),"confidence":round(abs(breadth-50)*2,1)}

def report(status,source,reason,stocks,universe_info=None,regime_stocks=None):
    times=[x.get("quote_time") for x in stocks if x.get("quote_time")]
    data_as_of=max(times) if times else None
    payload={"status":status,"timestamp":utc_now(),"data_as_of":data_as_of or utc_now(),
             "data_as_of_basis":"PROVIDER_QUOTE_TIME" if times else "NONE",
             "source":source,"reason":reason,"paper_only":True,"universe":universe_info or {},
             "universe_count":len(stocks),"regime":derive_regime(regime_stocks if regime_stocks is not None else stocks),"stocks":stocks}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return payload

def nse_session():
    import http.cookiejar
    op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.open(urllib.request.Request(NSE_HOME,headers=NSE_HEADERS),timeout=20).read(); return op

def nse_quote(op,symbol):
    with op.open(urllib.request.Request(NSE_QUOTE_URL+urllib.parse.quote(symbol),headers=NSE_HEADERS),timeout=20) as r:d=json.loads(r.read().decode())
    p=d.get("priceInfo",{}); price=p.get("lastPrice")
    if price is None:raise RuntimeError("NSE quote missing lastPrice")
    return {"symbol":symbol,"price":float(price),"change":float(p["pChange"]) if p.get("pChange") is not None else None,
            "open":p.get("open"),"high":p.get("intraDayHighLow",{}).get("max"),"low":p.get("intraDayHighLow",{}).get("min"),
            "prev_close":p.get("previousClose"),"volume":d.get("marketDeptOrderBook",{}).get("tradeInfo",{}).get("totalTradedVolume"),"security_id":None,
            "quote_time":utc_now()}

def yahoo_quote(symbol):
    ticker=urllib.parse.quote(symbol.replace("&","%26")+".NS",safe="")
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
    payload=json.loads(fetch(url,{"User-Agent":"Mozilla/5.0","Accept":"application/json"},12).decode())
    result=(payload.get("chart",{}).get("result") or [None])[0]; meta=(result or {}).get("meta",{})
    price=meta.get("regularMarketPrice"); prev=meta.get("previousClose",meta.get("chartPreviousClose"))
    if price is None:raise RuntimeError("Yahoo price unavailable")
    return {"symbol":symbol,"price":float(price),"change":round((float(price)-float(prev))/float(prev)*100,2) if prev else None,
            "open":meta.get("regularMarketDayOpen"),"high":meta.get("regularMarketDayHigh"),"low":meta.get("regularMarketDayLow"),
            "prev_close":prev,"volume":meta.get("regularMarketVolume"),"security_id":None,"quote_time":utc_now()}

def fallback_quotes(symbols):
    rows=[];errors=[]
    try:
        op=nse_session()
        for s in symbols:
            try:rows.append(nse_quote(op,s))
            except Exception as e:errors.append(f"{s}: {e}")
        if rows:return rows,errors,"NSE India"
    except Exception as e:errors.append(str(e))
    rows=[] 
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(yahoo_quote,s):s for s in symbols}
        for f in concurrent.futures.as_completed(futures):
            s=futures[f]
            try:rows.append(f.result())
            except Exception as e:errors.append(f"{s}: {e}")
    rows.sort(key=lambda x:x["symbol"])
    if rows:return rows,errors,"Yahoo Finance"
    raise RuntimeError("; ".join(errors[:10]) or "no fallback quotes")

def dhan_scan(client_id,token):
    ids,source=load_master(fetch)
    rows=[]
    items=list(ids.items())
    for start in range(0,len(items),BATCH):
        chunk=dict(items[start:start+BATCH])
        body=json.dumps({"NSE_EQ":[int(x) for x in chunk.values()]}).encode()
        payload=json.loads(fetch(MARKETFEED_URL,{"access-token":token,"client-id":client_id,"Content-Type":"application/json","Accept":"application/json"},body).decode())
        rows.extend(normalise_dhan(payload,chunk)); time.sleep(1.1)
    if not rows:raise RuntimeError("Dhan returned no usable NSE equity quotes")
    selected,stats=universe.select_candidates(rows,top_n=TOP_N,max_price=BUDGET)
    save_selected([x["symbol"] for x in selected],ids,"DHAN_FULL_MARKET_SCAN")
    info={"mode":"DYNAMIC_FULL_NSE_SCAN","source":source,"instruments":len(ids),"scanned":stats["scanned"],"selected":stats["selected"],"ranking":stats}
    return report("LIVE_MARKET_DATA","Dhan market feed",{"universe_source":source},selected,info,rows)

def main():
    cid=(os.getenv("DHAN_CLIENT_ID") or "").strip(); token=(os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
    dhan_error=None
    if cid and token:
        try:dhan_scan(cid,token); print("Dynamic full-NSE Dhan scan complete"); return 0
        except Exception as e:dhan_error=str(e)
    else:dhan_error="DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN not configured"
    symbols,ids,carried_at=load_carried()
    if symbols:
        try:
            rows,errors,source=fallback_quotes(symbols)
            selected,stats=select_candidates(rows,top_n=TOP_N,max_price=BUDGET)
            info={"mode":"CARRIED_DYNAMIC","source":source,"discovered_at":carried_at,"instruments":len(symbols),"scanned":len(rows),"selected":len(selected),"ranking":stats}
            report("LIVE_MARKET_DATA_FALLBACK",source,{"dhan_error":dhan_error,"fallback_errors":errors},selected,info); return 0
        except Exception as e: carried_error=str(e)
    else: carried_error="no recent live-discovered universe"
    try:
        symbols,stats,session=bhavcopy_universe(fetch,TOP_N,BUDGET)
        rows,errors,source=fallback_quotes(symbols)
        info={"mode":"BHAVCOPY_PREVIOUS_SESSION","source":source,"session_date":session,"instruments":len(symbols),"scanned":len(rows),"selected":len(rows),"ranking":stats}
        report("LIVE_MARKET_DATA_FALLBACK",source,{"dhan_error":dhan_error,"carried_error":carried_error,"fallback_errors":errors},rows,info); return 0
    except Exception as e:
        report("DATA_UNAVAILABLE","none",{"dhan_error":dhan_error,"carried_error":carried_error,"bhavcopy_error":str(e)},[],{"mode":"DATA_UNAVAILABLE","instruments":0,"scanned":0,"selected":0})
        print("Market data unavailable; no trade universe",file=sys.stderr); return 0

if __name__=="__main__": raise SystemExit(main())
