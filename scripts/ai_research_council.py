#!/usr/bin/env python3
"""Paper-only AI research council with graceful single-provider fallback."""
from __future__ import annotations
import json, os, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT=Path("public/data/market_snapshot.json")
SCRAP=Path("public/data/scrap_analysis.json")
OUT=Path("public/data/ai_research_council.json")
ALLOWED={"SUPPORTS_REVIEW","WATCH_ONLY","NO_SUPPORT"}
VALID_MARKET={"LIVE_MARKET_DATA","LIVE_MARKET_DATA_NSE","LIVE_MARKET_DATA_NSE_PROXY","LIVE_MARKET_DATA_FALLBACK"}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def load(p,f):
    try:
        x=json.loads(p.read_text(encoding="utf-8")); return x if isinstance(x,dict) else f
    except (OSError,json.JSONDecodeError): return f
def write(x):
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(x,indent=2),encoding="utf-8")
def config():
    return {"openai":{"api_key_configured":bool(os.getenv("OPENAI_API_KEY")),"model":os.getenv("OPENAI_MODEL") or None},"anthropic":{"api_key_configured":bool(os.getenv("ANTHROPIC_API_KEY")),"model":os.getenv("ANTHROPIC_MODEL") or None}}
def post(url,headers,payload):
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={**headers,"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode())
def oa_text(x):
    return "\n".join(c["text"] for i in x.get("output",[]) for c in (i.get("content",[]) if isinstance(i,dict) else []) if c.get("type") in ("output_text","text") and c.get("text")).strip()
def an_text(x):
    return "\n".join(i.get("text","") for i in x.get("content",[]) if isinstance(i,dict) and i.get("type")=="text").strip()
def classify(t):
    m=re.search(r"(?:^|\n)\s*CLASSIFICATION\s*:\s*(SUPPORTS_REVIEW|WATCH_ONLY|NO_SUPPORT)\b",t or "",re.I)
    return m.group(1).upper() if m else None
def call_openai(prompt,evidence):
    key,model=os.getenv("OPENAI_API_KEY"),os.getenv("OPENAI_MODEL")
    if not key or not model: return "","OpenAI not configured."
    try:
        x=post("https://api.openai.com/v1/responses",{"Authorization":f"Bearer {key}"},{"model":model,"input":prompt+"\n\nEVIDENCE:\n"+json.dumps(evidence,sort_keys=True),"store":False})
        t=oa_text(x); return (t,None) if t else ("","OpenAI returned no text.")
    except Exception as e: return "",f"OpenAI unavailable: {e}"
def call_anthropic(prompt,evidence):
    key,model=os.getenv("ANTHROPIC_API_KEY"),os.getenv("ANTHROPIC_MODEL")
    if not key or not model: return "","Anthropic not configured."
    try:
        x=post("https://api.anthropic.com/v1/messages",{"x-api-key":key,"anthropic-version":"2023-06-01"},{"model":model,"max_tokens":1400,"messages":[{"role":"user","content":prompt+"\n\nEVIDENCE:\n"+json.dumps(evidence,sort_keys=True)}]})
        t=an_text(x); return (t,None) if t else ("","Anthropic returned no text.")
    except Exception as e: return "",f"Anthropic unavailable: {e}"

def main():
    if not SNAPSHOT.exists():
        write({"status":"AI_UNAVAILABLE","paper_only":True,"reason":"Market snapshot missing.","execution_authorized":False})
        return 0
    market=load(SNAPSHOT,{"status":"DATA_UNAVAILABLE","stocks":[]})
    scrap=load(SCRAP,{"status":"NOT_RUN","stocks":[]})
    if market.get("status") not in VALID_MARKET:
        write({"status":"AI_UNAVAILABLE","paper_only":True,"reason":"No validated market data available.","market_status":market.get("status"),"scrap_status":scrap.get("status"),"config":config(),"execution_authorized":False})
        return 0

    budget=max(1000.0,float(os.getenv("PAPER_ANALYSIS_BUDGET","1000") or 1000))
    affordable={str(q.get("symbol")) for q in market.get("stocks",[]) if q.get("price") is not None and float(q.get("price")) <= budget}
    fm=dict(market); fm["stocks"]=[q for q in market.get("stocks",[]) if str(q.get("symbol")) in affordable]
    fs=dict(scrap); fs["stocks"]=[q for q in scrap.get("stocks",[]) if str(q.get("symbol")) in affordable]
    evidence={"analysis_budget":budget,"budget_rule":"Dhan available funds when available; otherwise ₹1,000 paper minimum","market_snapshot":fm,"scrap_analysis":fs}
    prompt=("You are an advisory market-research analyst in a paper-trading system. Use only the supplied decision-time market and SCRAP evidence. Do not invent data. Assess technical evidence, contradictions, uncertainty and risk blind spots. Never issue an executable order. Start with exactly one line: CLASSIFICATION: SUPPORTS_REVIEW, WATCH_ONLY, or NO_SUPPORT.")

    ov,oe=call_openai(prompt,evidence); av,ae=call_anthropic(prompt,evidence)
    oc,ac=classify(ov),classify(av)
    available=[("OpenAI",ov,oc),("Anthropic",av,ac)]
    available=[x for x in available if x[1]]

    if len(available)==0:
        write({"status":"AI_UNAVAILABLE","timestamp":now(),"paper_only":True,"config":config(),"degraded_mode":True,
               "working_provider":None,"independent":{"openai":None,"anthropic":None},
               "independent_classifications":{"openai":None,"anthropic":None},
               "consensus":{"status":"AI_UNAVAILABLE","classification":None,"rule":"Continue deterministic paper gates without AI."},
               "errors":{"openai":oe,"anthropic":ae},"execution_authorized":False})
        return 0

    if len(available)==1:
        name,text_value,classification=available[0]
        write({"status":"DEGRADED_ONE_AI","timestamp":now(),"paper_only":True,"config":config(),"degraded_mode":True,
               "working_provider":name,"independent":{"openai":ov or None,"anthropic":av or None},
               "independent_classifications":{"openai":oc,"anthropic":ac},
               "cross_review":{"openai":None,"anthropic":None},
               "final_positions":{"openai":ov if name=="OpenAI" else None,"anthropic":av if name=="Anthropic" else None},
               "final_classifications":{"openai":oc,"anthropic":ac},
               "consensus":{"status":"DEGRADED_AGREEMENT" if classification else "DEGRADED_UNCLASSIFIED","classification":classification,"provider":name,
                            "rule":"Use the single available AI advisory result; ignore the unavailable AI for this cycle."},
               "errors":{"openai":oe,"anthropic":ae},"execution_authorized":False,
               "safety":{"live_orders_enabled":False,"ai_can_override_deterministic_gates":False,"stock_specific_rules_allowed":False}})
        return 0

    critique="Review the peer analysis against the same evidence. Identify unsupported claims, missing evidence, contradictions and risk blind spots. Never issue an executable order."
    ac_text,ace=call_anthropic(critique+"\n\nPEER OPENAI:\n"+ov,evidence)
    oc_text,oce=call_openai(critique+"\n\nPEER ANTHROPIC:\n"+av,evidence)
    final=("Reassess your classification using the peer analysis and critiques. State uncertainty and data gaps. Advisory only. Start with exactly one CLASSIFICATION line using SUPPORTS_REVIEW, WATCH_ONLY or NO_SUPPORT.")
    of,ofe=call_openai(final+"\n\nYOUR ANALYSIS:\n"+ov+"\n\nPEER:\n"+av+"\n\nCRITIQUE:\n"+oc_text,evidence)
    af,afe=call_anthropic(final+"\n\nYOUR ANALYSIS:\n"+av+"\n\nPEER:\n"+ov+"\n\nCRITIQUE:\n"+ac_text,evidence)
    fc1,fc2=classify(of),classify(af)
    if of and af and fc1 and fc2 and fc1==fc2:
        status,classification="COMPLETE",fc1
    elif of and af and fc1 and fc2:
        status,classification="DISAGREEMENT","HOLD_FOR_REVIEW"
    elif of or af:
        status,classification="DEGRADED_ONE_AI_FINAL","HOLD_FOR_REVIEW"
    else:
        status,classification="AI_UNAVAILABLE","HOLD_FOR_REVIEW"
    write({"status":status,"timestamp":now(),"paper_only":True,"config":config(),"degraded_mode":status.startswith("DEGRADED") or status=="AI_UNAVAILABLE",
           "working_provider":None if status=="COMPLETE" else ("OpenAI" if of and not af else "Anthropic" if af and not of else None),
           "independent":{"openai":ov,"anthropic":av},"independent_classifications":{"openai":oc,"anthropic":ac},
           "cross_review":{"openai":oc_text,"anthropic":ac_text},"final_positions":{"openai":of or None,"anthropic":af or None},
           "final_classifications":{"openai":fc1,"anthropic":fc2},
           "consensus":{"status":status,"classification":classification,"rule":"Exact agreement required when both final analyses exist; a single working final analysis may be used only in degraded mode."},
           "errors":{"openai":oe,"anthropic":ae,"openai_cross_review":oce,"anthropic_cross_review":ace,"openai_final":ofe,"anthropic_final":afe},
           "execution_authorized":False,"safety":{"live_orders_enabled":False,"ai_can_override_deterministic_gates":False,"stock_specific_rules_allowed":False,"disagreement_defaults_to_hold":True}})
    return 0

if __name__=="__main__":
    raise SystemExit(main())
