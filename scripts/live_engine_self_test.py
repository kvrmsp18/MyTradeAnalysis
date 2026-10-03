#!/usr/bin/env python3
"""Offline safety tests for the live execution path. Never calls Dhan."""
from __future__ import annotations
import os, tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dhan_order

def test_live_gate():
    old={k:os.environ.get(k) for k in ("DHAN_CLIENT_ID","DHAN_ACCESS_TOKEN","DHAN_API_KEY","LIVE_TRADING_ENABLED","LIVE_TRADING_CONFIRMATION")}
    for k in old: os.environ.pop(k,None)
    try:
        try:
            dhan_order.config_from_env()
        except dhan_order.LiveOrderBlocked:
            pass
        else:
            raise AssertionError("missing credentials must block")
        os.environ.update({
            "DHAN_CLIENT_ID":"test","DHAN_ACCESS_TOKEN":"test","DHAN_API_KEY":"test",
            "LIVE_TRADING_ENABLED":"0","LIVE_TRADING_CONFIRMATION":"I_UNDERSTAND_LIVE_ORDERS"})
        try:
            dhan_order.config_from_env()
        except dhan_order.LiveOrderBlocked:
            pass
        else:
            raise AssertionError("disabled live gate must block")
        os.environ["LIVE_TRADING_ENABLED"]="1"
        os.environ["LIVE_TRADING_CONFIRMATION"]="WRONG"
        try:
            dhan_order.config_from_env()
        except dhan_order.LiveOrderBlocked:
            pass
        else:
            raise AssertionError("wrong confirmation must block")
        os.environ["LIVE_TRADING_CONFIRMATION"]="I_UNDERSTAND_LIVE_ORDERS"
        cfg=dhan_order.config_from_env()
        assert cfg.client_id=="test"
    finally:
        for k,v in old.items():
            if v is None: os.environ.pop(k,None)
            else: os.environ[k]=v

def main():
    test_live_gate()
    print("LIVE ENGINE SAFETY SELF-TEST: PASS")
if __name__=="__main__":
    main()
