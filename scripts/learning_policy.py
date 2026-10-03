#!/usr/bin/env python3
"""Bounded, symbol-agnostic EOD learning policy."""
from __future__ import annotations
import json, os
from pathlib import Path

POLICY=Path("data/learning/policy.json")
LEARNING_ENABLED=os.getenv("LEARNING_ENABLED","1").strip()!="0"
MAX_DRIFT_FRACTION=0.15
BASE={"scrap_review_cutoff":70,"review_score":65,"universe_top_n":60}
FLOOR={"scrap_review_cutoff":60,"review_score":55}
CEILING={"universe_top_n":100}
STEP={"scrap_review_cutoff":1,"review_score":1,"universe_top_n":5}

def load_policy():
    try:
        p=json.loads(POLICY.read_text(encoding="utf-8"))
        return p if isinstance(p,dict) else {}
    except (OSError,json.JSONDecodeError): return {}

def clamp(key,value):
    lo=BASE[key]*(1-MAX_DRIFT_FRACTION); hi=BASE[key]*(1+MAX_DRIFT_FRACTION)
    if key in FLOOR: lo=max(lo,FLOOR[key])
    if key in CEILING: hi=min(hi,CEILING[key])
    return int(round(max(lo,min(hi,value))))

def apply_learning(day_stats, patterns):
    current=load_policy()
    effective={k:clamp(k,int(current.get("effective",{}).get(k,v))) for k,v in BASE.items()}
    changes=[]; skipped=[]
    if not LEARNING_ENABLED:
        return {"enabled":False,"effective":effective,"changes":[],"skipped":["LEARNING_ENABLED=0"]}
    net=float(day_stats.get("net_pnl",0) or 0)
    stops=int(day_stats.get("stop_losses",0) or 0)
    for p in patterns:
        reason=str(p.get("pattern") or p.get("reason") or "")
        action=str(p.get("action") or "")
        if not reason: continue
        direction=None
        if action=="LOOSEN" and net>=0: direction=1
        elif action=="TIGHTEN" and net<0 and stops>=2: direction=-1
        elif action in {"LOOSEN","TIGHTEN"} and net<0: skipped.append(f"{reason}: losing day blocks loosening")
        else: skipped.append(f"{reason}: REPORT_ONLY")
        if direction is None: continue
        key={"SCRAP_WATCH_ONLY":"scrap_review_cutoff","EXECUTION_FEATURE_SCORE_BELOW_THRESHOLD":"review_score",
             "NOT_IN_PAPER_CANDIDATE_UNIVERSE_SETUP":"universe_top_n", "NOT_IN_PAPER_CANDIDATE_UNIVERSE_WITH_RECONSTRUCTED_SETUP":"universe_top_n"}.get(reason)
        if not key: skipped.append(f"{reason}: unmapped"); continue
        new=clamp(key,effective[key]+direction*STEP[key])
        if new!=effective[key]:
            changes.append({"reason":reason,"setting":key,"old":effective[key],"new":new,"step":direction*STEP[key]})
            effective[key]=new
    payload={"enabled":True,"base":BASE,"effective":effective,"changes":changes,"skipped":skipped,
             "bounds":{"max_drift_fraction":MAX_DRIFT_FRACTION},"source":"EOD_GENERAL_PATTERNS"}
    POLICY.parent.mkdir(parents=True,exist_ok=True); POLICY.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return payload
