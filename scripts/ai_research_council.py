#!/usr/bin/env python3
"""Paper-only, provider-agnostic AI research council."""
from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from ai_clients import call_anthropic,call_openai,classify

SNAPSHOT=Path("public/data/market_snapshot.json"); SCRAP=Path("public/data/scrap_analysis.json")
OUT=Path("public/data/ai_research_council.json")
VALID_MARKET={"LIVE_MARKET_DATA","LIVE_MARKET_DATA_NSE","LIVE_MARKET_DATA_NSE_PROXY","LIVE_MARKET_DATA_FALLBACK"}
def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def load(p,d):
    try:
        x=json.loads(p.read_text(encoding="utf-8")); return x if isinstance(x,dict) else d
    except (OSError,json.JSONDecodeError): return d
def write(x): OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(x,indent=2),encoding="utf-8")
def config(): return {"openai":{"api_key_configured":bool(os.getenv("OPENAI_API_KEY")),"model":os.getenv("OPENAI_MODEL") or None},"anthropic":{"api_key_configured":bool(os.getenv("ANTHROPIC_API_KEY")),"model":os.getenv("ANTHROPIC_MODEL") or None}}
def in_session():
    if os.getenv("AI_COUNCIL_FORCE")=="1": return True
    t=datetime.now(ZoneInfo("Asia/Kolkata")); m=t.hour*60+t.minute
    return t.weekday()<5 and 9*60+15<=m<=15*60+30
def minutes_since(ts):
    try: return (datetime.now(timezone.utc)-datetime.fromisoformat(str(ts).replace("Z","+00:00"))).total_seconds()/60
    except Exception: return 999999
def affordable_evidence(market,scrap):
    budget=max(1000.0,float(os.getenv("PAPER_ANALYSIS_BUDGET","1000") or 1000))
    allowed={str(q.get("symbol")) for q in market.get("stocks",[]) if q.get("price") is not None and float(q.get("price"))<=budget}
    fm=dict(market); fm["stocks"]=[q for q in market.get("stocks",[]) if str(q.get("symbol")) in allowed]
    fs=dict(scrap); fs["stocks"]=[q for q in scrap.get("stocks",[]) if str(q.get("symbol")) in allowed]
    return {"analysis_budget":budget,"budget_rule":"Dhan available funds when available; otherwise ₹1,000 paper minimum","market_snapshot":fm,"scrap_analysis":fs}
def main():
    if not in_session():
        write({"status":"AI_OUT_OF_SESSION","timestamp":now(),"paper_only":True,"execution_authorized":False,"reason":"AI council runs only during NSE session unless AI_COUNCIL_FORCE=1."}); return 0
    market=load(SNAPSHOT,{"status":"DATA_UNAVAILABLE","stocks":[]}); scrap=load(SCRAP,{"status":"NOT_RUN","stocks":[]})
    if market.get("status") not in VALID_MARKET:
        write({"status":"AI_UNAVAILABLE","timestamp":now(),"paper_only":True,"reason":"No validated market data available.","config":config(),"execution_authorized":False}); return 0
    evidence=affordable_evidence(market,scrap)
    fingerprint=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()
    previous=load(OUT,{})
    if previous.get("evidence_fingerprint")==fingerprint and previous.get("status") in {"COMPLETE","DEGRADED_ONE_AI","DEGRADED_ONE_AI_FINAL"} and minutes_since(previous.get("timestamp"))<=30:
        previous["reused_within_30m"]=True; write(previous); return 0
    prompt=("You are an advisory market-research analyst. Use only the supplied decision-time evidence. "
            "Do not invent data. Assess technical evidence, contradictions, uncertainty and risk blind spots. "
            "Never issue an executable order. Start with exactly one line: CLASSIFICATION: SUPPORTS_REVIEW, WATCH_ONLY, or NO_SUPPORT.")
    results={}; errors={}
    for name,call in (("OpenAI",call_openai),("Anthropic",call_anthropic)):

        text,error=call(prompt,evidence,max_output_tokens=3000)
        if text:
            results[name]=text
        else: errors[name.lower()]=error
    ov,av=results.get("OpenAI",""),results.get("Anthropic","")
    oc,ac=classify(ov),classify(av)
    if not ov and not av:
        previous=load(OUT,{})
        if previous.get("status")=="AI_UNAVAILABLE" and minutes_since(previous.get("timestamp"))<10:
            errors["backoff"]="10-minute retry backoff after AI failure."
        write({"status":"AI_UNAVAILABLE","timestamp":now(),"paper_only":True,"config":config(),"degraded_mode":True,
               "working_provider":None,"independent":{"openai":None,"anthropic":None},
               "independent_classifications":{"openai":None,"anthropic":None},"errors":errors,
               "consensus":{"status":"AI_UNAVAILABLE","classification":None,"rule":"No AI available; deterministic paper analysis continues."},
               "execution_authorized":False,"safety":{"live_orders_enabled":False,"ai_can_override_deterministic_gates":False,"stock_specific_rules_allowed":False}})
        return 0
    if bool(ov)!=bool(av):
        name="OpenAI" if ov else "Anthropic"; cls=oc if ov else ac
        write({"evidence_fingerprint":fingerprint,"status":"DEGRADED_ONE_AI","timestamp":now(),"paper_only":True,"config":config(),"degraded_mode":True,
               "working_provider":name,"independent":{"openai":ov or None,"anthropic":av or None},
               "independent_classifications":{"openai":oc,"anthropic":ac},"final_classifications":{"openai":oc,"anthropic":ac},
               "errors":errors,"consensus":{"status":"DEGRADED_ONE_AI","classification":cls,"provider":name,
               "rule":"Use every available AI provider; ignore unavailable providers for this cycle."},
               "execution_authorized":False,"safety":{"live_orders_enabled":False,"ai_can_override_deterministic_gates":False,"stock_specific_rules_allowed":False}})
        cache["council_result"]={"timestamp":now(),"fingerprint":fingerprint,"result":load(OUT,{})}
        CACHE.write_text(json.dumps(cache,indent=2),encoding="utf-8")
        return 0

    critique=("Review the peer analysis against the same evidence. Identify unsupported claims, missing evidence, contradictions and risk blind spots. Advisory only.")
    ac_text,ace=call_anthropic(critique+"\n\nPEER OPENAI:\n"+ov,evidence,max_output_tokens=3000)
    oc_text,oce=call_openai(critique+"\n\nPEER ANTHROPIC:\n"+av,evidence,max_output_tokens=3000)
    final=("Reassess your classification using the peer analysis and critique. State uncertainty and data gaps. "
           "Advisory only. Start with exactly one CLASSIFICATION line using SUPPORTS_REVIEW, WATCH_ONLY or NO_SUPPORT.")
    of,ofe=call_openai(final+"\n\nYOUR ANALYSIS:\n"+ov+"\n\nPEER:\n"+av+"\n\nCRITIQUE:\n"+oc_text,evidence,max_output_tokens=3000)
    af,afe=call_anthropic(final+"\n\nYOUR ANALYSIS:\n"+av+"\n\nPEER:\n"+ov+"\n\nCRITIQUE:\n"+ac_text,evidence,max_output_tokens=3000)
    fc1,fc2=classify(of),classify(af)
    if fc1 and fc2 and fc1==fc2: status,classification="COMPLETE",fc1
    elif fc1 and fc2: status,classification="DISAGREEMENT","HOLD_FOR_REVIEW"
    elif fc1 or fc2: status,classification="DEGRADED_ONE_AI_FINAL",fc1 or fc2
    else: status,classification="AI_UNAVAILABLE",None
    write({"evidence_fingerprint":fingerprint,"status":status,"timestamp":now(),"paper_only":True,"config":config(),"degraded_mode":status.startswith("DEGRADED") or status=="AI_UNAVAILABLE",
           "working_provider":None if status=="COMPLETE" else ("OpenAI" if fc1 and not fc2 else "Anthropic" if fc2 and not fc1 else None),
           "independent":{"openai":ov,"anthropic":av},"independent_classifications":{"openai":oc,"anthropic":ac},
           "cross_review":{"openai":oc_text or None,"anthropic":ac_text or None},
           "final_positions":{"openai":of or None,"anthropic":af or None},
           "final_classifications":{"openai":fc1,"anthropic":fc2},
           "errors":{"openai":errors.get("openai"),"anthropic":errors.get("anthropic"),"openai_cross_review":oce,"anthropic_cross_review":ace,"openai_final":ofe,"anthropic_final":afe},
           "consensus":{"status":status,"classification":classification,"rule":"Use all available provider results; disagreements default to HOLD_FOR_REVIEW; no vendor is mandatory."},
           "execution_authorized":False,"safety":{"live_orders_enabled":False,"ai_can_override_deterministic_gates":False,"stock_specific_rules_allowed":False,"disagreement_defaults_to_hold":True}})
    return 0
if __name__=="__main__": raise SystemExit(main())
