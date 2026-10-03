#!/usr/bin/env python3
"""Paper-only AI research council with independent per-share verdicts."""
from __future__ import annotations
import hashlib,json,os,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ai_clients import call_openai,call_anthropic,classify,parse_symbol_verdicts,combine_symbol_verdicts

SNAPSHOT=Path("public/data/market_snapshot.json"); SCRAP=Path("public/data/scrap_analysis.json"); OUT=Path("public/data/ai_research_council.json")
VALID={"LIVE_MARKET_DATA","LIVE_MARKET_DATA_NSE","LIVE_MARKET_DATA_NSE_PROXY","LIVE_MARKET_DATA_FALLBACK"}
SAFETY={"live_orders_enabled":False,"ai_can_override_deterministic_gates":False,"stock_specific_rules_allowed":False}
def now():return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def load(p,d):
    try:
        x=json.loads(p.read_text(encoding="utf-8")); return x if isinstance(x,dict) else d
    except (OSError,json.JSONDecodeError):return d
def write(x):OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(x,indent=2),encoding="utf-8")
def session():
    if os.getenv("AI_COUNCIL_FORCE")=="1":return True
    t=datetime.now(ZoneInfo("Asia/Kolkata"));m=t.hour*60+t.minute
    return t.weekday()<5 and 555<=m<=930
def mins(ts):
    try:return (datetime.now(timezone.utc)-datetime.fromisoformat(str(ts).replace("Z","+00:00"))).total_seconds()/60
    except Exception:return 999999
def build_evidence(m,s):
    budget=max(1000.0,float(os.getenv("PAPER_ANALYSIS_BUDGET","1000") or 1000))
    allowed={str(x.get("symbol")) for x in m.get("stocks",[]) if x.get("price") is not None and float(x.get("price"))<=budget}
    fs=[x for x in s.get("stocks",[]) if str(x.get("symbol")) in allowed]
    ranked=sorted((x for x in fs if x.get("action")=="REVIEW" and x.get("score") is not None),key=lambda x:(-float(x["score"]),str(x.get("symbol"))))
    top=int(os.getenv("AI_SHORTLIST_SIZE","10") or 10)
    return {"analysis_budget":budget,"market_snapshot":{**m,"stocks":[x for x in m.get("stocks",[]) if str(x.get("symbol")) in allowed]},
            "scrap_analysis":{**s,"stocks":fs},"universe":m.get("universe"),"market_regime":m.get("regime"),
            "shortlist_for_verdicts":[str(x["symbol"]) for x in ranked[:top]]}

def main():
    if not session():
        write({"status":"AI_OUT_OF_SESSION","timestamp":now(),"paper_only":True,"execution_authorized":False,"reason":"Outside NSE session","safety":SAFETY});return 0
    market=load(SNAPSHOT,{"status":"DATA_UNAVAILABLE","stocks":[]});scrap=load(SCRAP,{"status":"NOT_RUN","stocks":[]})
    if market.get("status") not in VALID:
        write({"status":"AI_UNAVAILABLE","timestamp":now(),"paper_only":True,"execution_authorized":False,"reason":"No validated market data available","config":{},"safety":SAFETY});return 0
    evidence=build_evidence(market,scrap);fp=hashlib.sha256(json.dumps(evidence,sort_keys=True,default=str).encode()).hexdigest()
    previous=load(OUT,{})
    if previous.get("evidence_fingerprint")==fp and previous.get("status") in {"COMPLETE","DEGRADED_ONE_AI","DEGRADED_ONE_AI_FINAL"} and mins(previous.get("timestamp"))<=30:
        previous["reused_within_30m"]=True;write(previous);return 0
    base=("You are an advisory analyst inside a PAPER-trading system. Use only supplied evidence. "
          "Never issue an order or invent data. First line must be CLASSIFICATION: SUPPORTS_REVIEW, WATCH_ONLY, or NO_SUPPORT. "
          "Then for every symbol in shortlist_for_verdicts output exactly SYMBOL: SUPPORT, SYMBOL: WATCH, or SYMBOL: AVOID.")
    results={};errors={};backoff={}
    for name,fn in (("OpenAI",call_openai),("Anthropic",call_anthropic)):
        text,error=fn(base,evidence,max_output_tokens=3000)
        if text:results[name]=text
        else:errors[name.lower()]=error
    ov,av=results.get("OpenAI",""),results.get("Anthropic","");oc,ac=classify(ov),classify(av)
    if not ov and not av:
        write({"status":"AI_UNAVAILABLE","timestamp":now(),"paper_only":True,"execution_authorized":False,"independent":{"openai":None,"anthropic":None},
               "independent_classifications":{"openai":None,"anthropic":None},"candidate_verdicts":{},"errors":errors,
               "consensus":{"status":"AI_UNAVAILABLE","classification":None},"safety":SAFETY});return 0
    shortlist=evidence["shortlist_for_verdicts"]
    verdicts=combine_symbol_verdicts([parse_symbol_verdicts(x,shortlist) for x in (ov,av) if x])
    if bool(ov)!=bool(av):
        cls=oc if ov else ac; status="DEGRADED_ONE_AI"; classification=cls
        working="OpenAI" if ov else "Anthropic"; cross={}
    else:
        critique=("Review the peer analysis against the same evidence. Identify unsupported claims, contradictions and risk blind spots. Advisory only.")
        ac_text,ace=call_anthropic(critique+"\nPEER OPENAI:\n"+ov,evidence,max_output_tokens=3000)
        oc_text,oce=call_openai(critique+"\nPEER ANTHROPIC:\n"+av,evidence,max_output_tokens=3000)
        final=base+" Reassess using peer analysis and critique; preserve the required format."
        of,ofe=call_openai(final+"\nYOUR ANALYSIS:\n"+ov+"\nPEER:\n"+av+"\nCRITIQUE:\n"+oc_text,evidence,max_output_tokens=3000)
        af,afe=call_anthropic(final+"\nYOUR ANALYSIS:\n"+av+"\nPEER:\n"+ov+"\nCRITIQUE:\n"+ac_text,evidence,max_output_tokens=3000)
        fc1,fc2=classify(of),classify(af)
        if fc1 and fc2 and fc1==fc2:status,classification="COMPLETE",fc1
        elif fc1 and fc2:status,classification="DISAGREEMENT","HOLD_FOR_REVIEW"
        elif fc1 or fc2:status,classification="DEGRADED_ONE_AI_FINAL",fc1 or fc2
        else:status,classification="AI_UNAVAILABLE",None
        working=None;cross={"openai":oc_text or None,"anthropic":ac_text or None}
        errors.update({"openai_cross_review":oce,"anthropic_cross_review":ace,"openai_final":ofe,"anthropic_final":afe})
        final_verdicts=combine_symbol_verdicts([parse_symbol_verdicts(x,shortlist) for x in (of,af) if x])
        if final_verdicts:verdicts=final_verdicts
    write({"status":status,"timestamp":now(),"paper_only":True,"execution_authorized":False,"config":{
        "openai_api_key_configured":bool(os.getenv("OPENAI_API_KEY")),"anthropic_api_key_configured":bool(os.getenv("ANTHROPIC_API_KEY"))},
        "evidence_fingerprint":fp,"shortlist":shortlist,"independent":{"openai":ov or None,"anthropic":av or None},
        "independent_classifications":{"openai":oc,"anthropic":ac},"candidate_verdicts":{s:{"verdict":verdicts[s]} for s in sorted(verdicts)},
        "working_provider":working,"cross_review":cross,"errors":errors,
        "consensus":{"status":status,"classification":classification,"rule":"AVOID > WATCH > SUPPORT across available providers; market-wide NO_SUPPORT blocks all; AI never bypasses deterministic gates."},
        "safety":SAFETY})
    return 0
if __name__=="__main__":raise SystemExit(main())
