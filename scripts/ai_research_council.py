#!/usr/bin/env python3
"""Non-executing OpenAI + Anthropic research council for paper trading."""
from __future__ import annotations
import json, os, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT=Path("public/data/market_snapshot.json")
SCRAP=Path("public/data/scrap_analysis.json")
OUT=Path("public/data/ai_research_council.json")
ALLOWED={"SUPPORTS_REVIEW","WATCH_ONLY","NO_SUPPORT"}

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

def an_text(x): return "\n".join(i.get("text","") for i in x.get("content",[]) if isinstance(i,dict) and i.get("type")=="text").strip()

def classify(t):
    m=re.search(r"(?:^|\n)\s*CLASSIFICATION\s*:\s*(SUPPORTS_REVIEW|WATCH_ONLY|NO_SUPPORT)\b",t or "",re.I)
    return m.group(1).upper() if m and m.group(1).upper() in ALLOWED else None

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

def unavailable(reason,market=None,scrap=None):
    write({"status":"UNAVAILABLE","timestamp":now(),"paper_only":True,"reason":reason,"market_status":(market or {}).get("status"),"scrap_status":(scrap or {}).get("status"),"config":config(),"stages":{"market_evidence":"NOT_READY","independent_analysis":"NOT_RUN","cross_review":"NOT_RUN","final_positions":"NOT_RUN","consensus":"NOT_RUN"},"execution_authorized":False})
    return 0

def main():
    if not SNAPSHOT.exists(): return unavailable("Market snapshot missing.")
    market=load(SNAPSHOT,{"status":"DATA_UNAVAILABLE","stocks":[]}); scrap=load(SCRAP,{"status":"NOT_RUN","stocks":[]})
    if market.get("status") not in ("LIVE_MARKET_DATA","LIVE_MARKET_DATA_NSE","LIVE_MARKET_DATA_NSE_PROXY","LIVE_MARKET_DATA_FALLBACK"):
        return unavailable("No validated market data available.",market,scrap)
    analysis_budget = max(1000.0, float(os.getenv("PAPER_ANALYSIS_BUDGET", "1000") or 1000))
    affordable_symbols = {
        str(q.get("symbol"))
        for q in market.get("stocks", [])
        if q.get("price") is not None and float(q.get("price")) <= analysis_budget
    }
    filtered_market = dict(market)
    filtered_market["stocks"] = [
        q for q in market.get("stocks", [])
        if str(q.get("symbol")) in affordable_symbols
    ]
    filtered_scrap = dict(scrap)
    filtered_scrap["stocks"] = [
        row for row in scrap.get("stocks", [])
        if str(row.get("symbol")) in affordable_symbols
    ]
    evidence={"analysis_budget":analysis_budget,"budget_rule":"Dhan available funds when available; otherwise ₹1,000 paper minimum","market_snapshot":filtered_market,"scrap_analysis":filtered_scrap}
    stages={"market_evidence":"READY", "market_source": market.get("source"), "independent_analysis":"RUNNING","cross_review":"NOT_RUN","final_positions":"NOT_RUN","consensus":"NOT_RUN"}
    independent=("You are an independent market-research analyst in a paper-trading system. Use only the supplied decision-time market snapshot and deterministic SCRAP evidence. Do not invent data. Assess technical evidence, context, contradictions, uncertainty and risk blind spots. This is advisory research, not an order. Start with exactly: CLASSIFICATION: SUPPORTS_REVIEW, CLASSIFICATION: WATCH_ONLY, or CLASSIFICATION: NO_SUPPORT.")
    ov,oe=call_openai(independent,evidence); av,ae=call_anthropic(independent,evidence)
    if not ov or not av:
        stages["independent_analysis"]="QUORUM_UNAVAILABLE"
        write({"status":"QUORUM_UNAVAILABLE","timestamp":now(),"paper_only":True,"config":config(),"stages":stages,"independent":{"openai":ov or None,"anthropic":av or None},"classifications":{"openai":classify(ov),"anthropic":classify(av)},"cross_review":{"openai":None,"anthropic":None},"final_positions":{"openai":None,"anthropic":None},"consensus":{"status":"QUORUM_UNAVAILABLE","classification":"HOLD_FOR_REVIEW"},"errors":{"openai":oe,"anthropic":ae},"execution_authorized":False}); return 0
    stages["independent_analysis"]="COMPLETE"; stages["cross_review"]="RUNNING"
    critique="Review the peer analysis against the same market/SCRAP evidence. Identify unsupported claims, missing evidence, contradictions and risk blind spots. Do not issue an executable order."
    ac,ace=call_anthropic(critique+"\n\nPEER OPENAI:\n"+ov,evidence); oc,oce=call_openai(critique+"\n\nPEER ANTHROPIC:\n"+av,evidence)
    stages["cross_review"]="COMPLETE" if ac and oc else "INCOMPLETE"; stages["final_positions"]="RUNNING"
    final=("Reassess your original classification using the peer analysis, both cross-critiques and the same deterministic evidence. Explicitly state agreement, disagreement, uncertainty and data gaps. Advisory only; never authorize an order. Start with exactly one CLASSIFICATION line using SUPPORTS_REVIEW, WATCH_ONLY or NO_SUPPORT.")
    of,ofe=call_openai(final+"\n\nYOUR ANALYSIS:\n"+ov+"\n\nPEER:\n"+av+"\n\nYOUR CRITIQUE:\n"+oc+"\n\nPEER CRITIQUE:\n"+ac,evidence)
    af,afe=call_anthropic(final+"\n\nYOUR ANALYSIS:\n"+av+"\n\nPEER:\n"+ov+"\n\nYOUR CRITIQUE:\n"+ac+"\n\nPEER CRITIQUE:\n"+oc,evidence)
    stages["final_positions"]="COMPLETE" if of and af else "INCOMPLETE"
    ocf,acf=classify(of),classify(af)
    if not of or not af: cs,cc="QUORUM_UNAVAILABLE","HOLD_FOR_REVIEW"
    elif not ocf or not acf: cs,cc="CLASSIFICATION_UNAVAILABLE","HOLD_FOR_REVIEW"
    elif ocf==acf: cs,cc="AGREEMENT",ocf
    else: cs,cc="DISAGREEMENT","HOLD_FOR_REVIEW"
    stages["consensus"]=cs
    write({"status":"COMPLETE" if of and af else "SYNTHESIS_UNAVAILABLE","timestamp":now(),"paper_only":True,"config":config(),"stages":stages,"independent":{"openai":ov,"anthropic":av},"independent_classifications":{"openai":classify(ov),"anthropic":classify(av)},"cross_review":{"openai":oc,"anthropic":ac},"final_positions":{"openai":of or None,"anthropic":af or None},"final_classifications":{"openai":ocf,"anthropic":acf},"consensus":{"status":cs,"classification":cc,"rule":"Exact agreement only; otherwise HOLD_FOR_REVIEW."},"errors":{"openai":oe,"anthropic":ae,"openai_cross_review":oce,"anthropic_cross_review":ace,"openai_final":ofe,"anthropic_final":afe},"execution_authorized":False,"safety":{"live_orders_enabled":False,"ai_can_override_deterministic_gates":False,"stock_specific_rules_allowed":False,"disagreement_defaults_to_hold":True}})
    return 0

if __name__=="__main__": raise SystemExit(main())
