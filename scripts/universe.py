#!/usr/bin/env python3
"""Dynamic, symbol-agnostic NSE cash-equity universe discovery."""
from __future__ import annotations
import csv, io, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
BHAVCOPY_URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
CACHE_DIR = Path("data/universe")
MASTER_CACHE = CACHE_DIR / "nse_equity.json"
LAST_SELECTED = CACHE_DIR / "last_selected.json"
MASTER_MAX_AGE_HOURS = 20
CARRY_MAX_AGE_DAYS = 3
DEFAULT_TOP_N = 60
MIN_PRICE = 5.0

def now_utc(): return datetime.now(timezone.utc)
def iso(ts): return ts.isoformat().replace("+00:00","Z")

def _pick(row,*names):
    lowered={str(k).strip().lower():v for k,v in row.items()}
    for n in names:
        v=lowered.get(n.lower())
        if v not in (None,""): return str(v).strip()
    return ""

def _num(v):
    try:
        if v in (None,"","-"): return None
        return float(str(v).replace(",","").strip())
    except (TypeError,ValueError): return None

def parse_master(text):
    ids={}
    for row in csv.DictReader(io.StringIO(text)):
        exchange=_pick(row,"SEM_EXM_EXCH_ID","EXCH_ID","exchange").upper()
        segment=_pick(row,"SEM_SEGMENT","SEGMENT").upper()
        symbol=_pick(row,"SEM_TRADING_SYMBOL","TRADING_SYMBOL","symbol")
        sec=_pick(row,"SEM_SMST_SECURITY_ID","SEM_SECURITY_ID","SECURITY_ID","security_id")
        instrument=_pick(row,"SEM_INSTRUMENT_NAME","INSTRUMENT","instrument").upper()
        series=_pick(row,"SEM_SERIES","SERIES").upper()
        if exchange!="NSE" or segment not in {"E","EQUITY","NSE_EQ"} or not symbol or not sec: continue
        if instrument and any(x in instrument for x in ("FUT","OPT","INDEX")): continue
        if series and series!="EQ": continue
        ids.setdefault(symbol,sec)
    return ids

def load_master(fetch:Callable[[str],bytes],now=None):
    now=now or now_utc(); cached={}
    try: cached=json.loads(MASTER_CACHE.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError): pass
    ids=cached.get("ids") if isinstance(cached.get("ids"),dict) else {}
    try: fresh=now-datetime.fromisoformat(str(cached.get("generated_at")).replace("Z","+00:00"))<timedelta(hours=MASTER_MAX_AGE_HOURS)
    except (TypeError,ValueError): fresh=False
    if ids and fresh: return ids,"CACHE_FRESH"
    try:
        parsed=parse_master(fetch(MASTER_URL).decode("utf-8-sig","replace"))
        if len(parsed)<500: raise RuntimeError(f"instrument master parsed to only {len(parsed)} NSE EQ symbols")
        CACHE_DIR.mkdir(parents=True,exist_ok=True)
        MASTER_CACHE.write_text(json.dumps({"generated_at":iso(now),"ids":parsed},separators=(",",":")),encoding="utf-8")
        return parsed,"FETCHED"
    except Exception:
        if ids: return ids,"CACHE_STALE"
        raise

def _percentile(values):
    indexed=sorted((v,i) for i,v in enumerate(values) if v is not None)
    ranks=[0.0]*len(values)
    if not indexed: return ranks
    pos=0
    while pos<len(indexed):
        end=pos
        while end+1<len(indexed) and indexed[end+1][0]==indexed[pos][0]: end+=1
        rank=(pos+end)/2/max(len(indexed)-1,1)
        for k in range(pos,end+1): ranks[indexed[k][1]]=rank
        pos=end+1
    return ranks

def select_candidates(rows,top_n=DEFAULT_TOP_N,max_price=None):
    eligible=[]
    for row in rows:
        p,c=_num(row.get("price")),_num(row.get("change"))
        if p is None or c is None or p<MIN_PRICE or (max_price is not None and p>max_price): continue
        vol=_num(row.get("volume")); hi=_num(row.get("high")); lo=_num(row.get("low")); prev=_num(row.get("prev_close"))
        eligible.append({"row":row,"change":c,"turnover":p*vol if vol and vol>0 else None,
                         "range":(hi-lo)/prev*100 if hi is not None and lo is not None and prev else None})
    stats={"scanned":len(rows),"eligible":len(eligible),"liquid":0,"selected":0,"top_n":top_n,"max_price":max_price,"min_price":MIN_PRICE}
    if not eligible:return [],stats
    tr=_percentile([x["turnover"] for x in eligible]); mr=_percentile([x["change"] for x in eligible]); rr=_percentile([x["range"] for x in eligible])
    has_turn=any(x["turnover"] is not None for x in eligible); scored=[]
    for i,e in enumerate(eligible):
        if has_turn and tr[i]<0.5: continue
        score=(0.45*tr[i]+0.35*mr[i]+0.20*rr[i]) if has_turn else (0.6*mr[i]+0.4*rr[i])
        scored.append((score,str(e["row"].get("symbol")),e["row"]))
    scored.sort(key=lambda x:(-x[0],x[1])); stats["liquid"]=len(scored)
    selected=[{**r,"selection_score":round(s,4)} for s,_,r in scored[:max(1,int(top_n))]]
    stats["selected"]=len(selected); return selected,stats

def save_selected(symbols,ids,source,now=None):
    now=now or now_utc(); CACHE_DIR.mkdir(parents=True,exist_ok=True)
    LAST_SELECTED.write_text(json.dumps({"generated_at":iso(now),"source":source,"symbols":symbols,"ids":{s:ids[s] for s in symbols if s in ids}},separators=(",",":")),encoding="utf-8")

def load_carried(now=None):
    now=now or now_utc()
    try:
        d=json.loads(LAST_SELECTED.read_text(encoding="utf-8"))
        generated=datetime.fromisoformat(str(d["generated_at"]).replace("Z","+00:00"))
        if now-generated>timedelta(days=CARRY_MAX_AGE_DAYS): return [],{},None
        syms=[str(s) for s in d.get("symbols",[]) if s]
        return syms,{str(k):str(v) for k,v in (d.get("ids") or {}).items()},str(d["generated_at"])
    except (OSError,ValueError,KeyError,json.JSONDecodeError,TypeError): return [],{},None

def parse_bhavcopy(text):
    rows=[]
    for raw in csv.DictReader(io.StringIO(text)):
        row={str(k).strip().upper(): (v.strip() if isinstance(v,str) else v) for k,v in raw.items() if k}
        if row.get("SERIES")!="EQ": continue
        close,prev=_num(row.get("CLOSE_PRICE")),_num(row.get("PREV_CLOSE"))
        if close is None or not prev: continue
        rows.append({"symbol":row.get("SYMBOL"),"price":close,"prev_close":prev,"change":round((close-prev)/prev*100,2),
                     "open":_num(row.get("OPEN_PRICE")),"high":_num(row.get("HIGH_PRICE")),"low":_num(row.get("LOW_PRICE")),"volume":_num(row.get("TTL_TRD_QNTY"))})
    return rows

def bhavcopy_universe(fetch,top_n=DEFAULT_TOP_N,max_price=None,today=None):
    today=today or now_utc(); last="no session tried"
    for back in range(1,8):
        day=today-timedelta(days=back)
        if day.weekday()>=5: continue
        try: rows=parse_bhavcopy(fetch(BHAVCOPY_URL.format(ddmmyyyy=day.strftime("%d%m%Y"))).decode("utf-8-sig","replace"))
        except Exception as e: last=str(e); continue
        if len(rows)<500: last=f"bhavcopy {day.date()} had only {len(rows)} EQ rows"; continue
        selected,stats=select_candidates(rows,top_n,max_price)
        return [str(r["symbol"]) for r in selected],stats,day.strftime("%Y-%m-%d")
    raise RuntimeError("bhavcopy bootstrap unavailable: "+last)
