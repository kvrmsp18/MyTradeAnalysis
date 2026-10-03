#!/usr/bin/env python3
"""Offline acceptance tests for Patch 3 requirements."""
from __future__ import annotations
import importlib.util, json, os, re, tempfile
from pathlib import Path
S=Path(__file__).resolve().parent
import sys
sys.path.insert(0,str(S))

def load(n):
    spec=importlib.util.spec_from_file_location(n,S/(n+".py")); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_no_fixed_list():
    text=(S/"market_snapshot.py").read_text(encoding="utf-8")
    assert "NIFTY50_VALIDATION_BASKET" not in text and "SYMBOLS =" not in text
    offenders=[]
    pat=re.compile(r'(?:["\'][A-Z][A-Z0-9&\-]{1,14}["\']\s*,\s*){9,}')
    for p in S.glob("*.py"):
        if p.name.endswith("_test.py"): continue
        if pat.search(p.read_text(encoding="utf-8")): offenders.append(p.name)
    assert not offenders, offenders

def test_master_and_generic_ranking():
    u=load("universe")
    csv="SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_TRADING_SYMBOL,SEM_SERIES\n"
    csv+="\n".join(f"NSE,E,{1000+i},EQUITY,ZZ{i:04d},EQ" for i in range(700))
    csv+="\nNSE,E,9999,EQUITY,ZZBAD,BE\nBSE,E,8888,EQUITY,NOPE,EQ\n"
    ids=u.parse_master(csv); assert len(ids)==700
    rows=[{"symbol":f"ZZ{i:04d}","price":100+i%50,"change":(i%21)-10,"volume":10000+i*1000,"high":105+i%10,"low":95,"prev_close":100} for i in range(700)]
    sel,stats=u.select_candidates(rows,top_n=60,max_price=1000)
    assert stats["scanned"]==700 and len(sel)==60 and stats["selected"]==60
    assert len({x["symbol"] for x in sel})==60

def test_learning_bounds():
    lp=load("learning_policy")
    with tempfile.TemporaryDirectory() as td:
        old=lp.POLICY; old_enabled=lp.LEARNING_ENABLED; lp.LEARNING_ENABLED=True; lp.POLICY=Path(td)/"policy.json"
        r=lp.apply_learning({"net_pnl":0,"stop_losses":0},[{"pattern":"SCRAP_WATCH_ONLY","action":"LOOSEN"}])
        assert r["effective"]["scrap_review_cutoff"]==69
        r=lp.apply_learning({"net_pnl":-10,"stop_losses":2},[{"pattern":"SCRAP_WATCH_ONLY","action":"LOOSEN"}])
        assert r["effective"]["scrap_review_cutoff"]==69
        lp.POLICY=old; lp.LEARNING_ENABLED=old_enabled

def test_ai_parser():
    a=load("ai_clients")
    got=a.parse_symbol_verdicts("AAA: SUPPORT\nBBB: AVOID\nNOTREAL: WATCH",["AAA","BBB"])
    assert got=={"AAA":"SUPPORT","BBB":"AVOID"}
    assert a.combine_symbol_verdicts([{"AAA":"SUPPORT"},{"AAA":"AVOID"}])["AAA"]=="AVOID"

def main():
    for fn in (test_no_fixed_list,test_master_and_generic_ranking,test_learning_bounds,test_ai_parser): fn()
    print("DYNAMIC BOT SELF-TEST: PASS")
if __name__=="__main__": main()
