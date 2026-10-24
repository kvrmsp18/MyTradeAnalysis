#!/usr/bin/env python3
"""Offline tests for the LIVE executor's exit path and gates, using a fake broker (no network).

Why this exists: scripts/live_executor.py shipped with a stray line in manage_positions() that used
undefined names, so the first real target/stop/EOD exit would have crashed before any SELL order was
sent. The older live self-test never reached that code. These tests drive every exit branch.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
IST_DAY = "2026-01-01"  # a Thursday


class FakeBroker:
    def __init__(self, positions=None, funds=10000.0):
        self.orders, self.positions_, self.funds = [], positions or [], funds

    def module(self):
        m = types.ModuleType("dhan_order")

        class LiveOrderBlocked(RuntimeError):
            pass
        m.LiveOrderBlocked = LiveOrderBlocked
        m.config_from_env = lambda: None
        m.positions = lambda: list(self.positions_)
        m.available_funds = lambda: self.funds

        def submit_order(**kw):
            self.orders.append(kw)
            return {"orderId": f"OID{len(self.orders)}"}
        m.submit_order = submit_order
        m.order_detail = lambda oid: {"orderStatus": "TRADED"}
        m.is_fill_status = lambda v: str(v).upper() == "TRADED"
        return m


@contextlib.contextmanager
def sandbox(broker, clock_ist, **env):
    saved_env, cwd, saved_mod = dict(os.environ), os.getcwd(), sys.modules.get("dhan_order")
    with tempfile.TemporaryDirectory() as td:
        try:
            os.environ.update({"TRADING_MODE": "LIVE", "LIVE_KILL_SWITCH": "0", "LIVE_MAX_DAILY_LOSS": "500",
                               "LIVE_MAX_DATA_AGE_MINUTES": "5", **{k: str(v) for k, v in env.items()}})
            os.chdir(td)
            sys.modules["dhan_order"] = broker.module()
            spec = importlib.util.spec_from_file_location("live_executor_under_test", SCRIPTS / "live_executor.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            hh, mm = map(int, clock_ist.split(":"))
            fixed = datetime(2026, 1, 1, hh, mm, tzinfo=mod.ZoneInfo("Asia/Kolkata"))
            mod.market_clock = lambda: (fixed, fixed.hour * 60 + fixed.minute)
            yield mod, Path(td)
        finally:
            os.chdir(cwd)
            os.environ.clear()
            os.environ.update(saved_env)
            if saved_mod is not None:
                sys.modules["dhan_order"] = saved_mod
            else:
                sys.modules.pop("dhan_order", None)


def seed(root, *, candidates=(), fresh=True, snap_status="LIVE_MARKET_DATA"):
    (root / "public/data").mkdir(parents=True, exist_ok=True)
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=1 if fresh else 60)).isoformat().replace("+00:00", "Z")
    stocks = [{"symbol": c["symbol"], "price": c["price"], "security_id": c["security_id"]} for c in candidates]
    (root / "public/data/market_snapshot.json").write_text(json.dumps({"status": snap_status, "data_as_of": stamp, "stocks": stocks}))
    led = root / "data/ledger" / IST_DAY
    led.mkdir(parents=True, exist_ok=True)
    (led / "000001.json").write_text(json.dumps({"mode": "PAPER", "candidates": [{
        "symbol": c["symbol"], "ranking": i + 1, "decision": "REVIEW", "features": {"score": 80},
        "scrap_result": {"score": 75}, "ai_council": {"status": c.get("ai_status", "COMPLETE"), "symbol_verdict": c.get("verdict", "SUPPORT")}}
        for i, c in enumerate(candidates)]}))


def pos(symbol="AA", qty=3, avg=100.0, ltp=100.0, sec="11", product="INTRADAY"):
    return {"tradingSymbol": symbol, "netQty": qty, "buyAvg": avg, "lastTradedPrice": ltp, "securityId": sec, "productType": product}


def run(mod):
    with contextlib.redirect_stdout(io.StringIO()):
        return mod.main()


def test_exit_branches_send_sell_orders():
    for label, ltp, clock, reason in (("target", 102.5, "11:00", "TARGET"), ("stop", 98.5, "11:00", "STOP_LOSS"), ("eod", 100.2, "15:29", "EOD_EXIT"), ("eod early", 100.2, "15:15", "EOD_EXIT")):
        b = FakeBroker([pos(ltp=ltp)])
        with sandbox(b, clock) as (mod, root):
            seed(root)
            assert run(mod) == 0
            sells = [o for o in b.orders if o["transaction_type"] == "SELL"]
            assert len(sells) == 1 and sells[0]["quantity"] == 3 and sells[0]["security_id"] == "11", (label, b.orders)
            assert sells[0]["product_type"] == "INTRADAY" and sells[0]["exchange_segment"] == "NSE_EQ"
            state = json.loads((root / "data/live/state.json").read_text())
            assert state["trades"][-1]["reason"] == reason and state["trades"][-1]["order_id"] == "OID1"


def test_no_exit_when_nothing_triggers_and_target_stop_need_fresh_data_but_eod_does_not():
    b = FakeBroker([pos(ltp=100.5)])
    with sandbox(b, "11:00") as (mod, root):
        seed(root)
        run(mod)
        assert not [o for o in b.orders if o["transaction_type"] == "SELL"]
    # stale data: live executor fails closed before ordering anything (including entries)
    b = FakeBroker([pos(ltp=103)])
    with sandbox(b, "11:00") as (mod, root):
        seed(root, fresh=False)
        assert run(mod) == 0 and b.orders == []


def test_gates_fail_closed():
    for env, clock, why in (({"TRADING_MODE": "PAPER"}, "11:00", "paper mode"), ({"LIVE_KILL_SWITCH": "1"}, "11:00", "kill switch"),
                            ({}, "08:00", "before session"), ({}, "15:45", "after session")):
        b = FakeBroker([pos(ltp=103)])
        with sandbox(b, clock, **env) as (mod, root):
            seed(root)
            run(mod)
            assert b.orders == [], why
            assert json.loads((root / "public/data/live_state.json").read_text())["status"] == "BLOCKED", why


def test_entry_rules_and_funds():
    cands = [{"symbol": "BB", "price": 50.0, "security_id": "22"}, {"symbol": "CC", "price": 40.0, "security_id": "33", "verdict": "WATCH"}]
    b = FakeBroker([], funds=10000.0)
    with sandbox(b, "11:00") as (mod, root):
        seed(root, candidates=cands)
        run(mod)
        buys = [o for o in b.orders if o["transaction_type"] == "BUY"]
        assert [o["security_id"] for o in buys] == ["22"], "only the AI-SUPPORTed share may be bought"
        assert buys[0]["quantity"] == int(10000 * 20 / 100 // 50) == 40
    b = FakeBroker([], funds=0.0)
    with sandbox(b, "11:00") as (mod, root):
        seed(root, candidates=cands)
        run(mod)
        assert b.orders == [], "no funds -> no order"
    b = FakeBroker([pos("A", ltp=100), pos("B", sec="12", ltp=100)])
    with sandbox(b, "11:00") as (mod, root):
        seed(root, candidates=cands)
        run(mod)
        assert [o for o in b.orders if o["transaction_type"] == "BUY"] == [], "max positions reached"


def test_daily_loss_blocks_entries_but_never_exits_and_resets_next_day():
    cands = [{"symbol": "BB", "price": 50.0, "security_id": "22"}]
    b = FakeBroker([pos(ltp=98.0)])  # stop-loss exit due
    with sandbox(b, "11:00") as (mod, root):
        seed(root, candidates=cands)
        (root / "data/live").mkdir(parents=True)
        (root / "data/live/state.json").write_text(json.dumps({"positions": {}, "trades": [], "daily_pnl": -900.0, "trading_day": "2026-01-01"}))
        run(mod)
        sides = [o["transaction_type"] for o in b.orders]
        assert sides == ["SELL"], f"loss limit must stop BUYs but still allow the protective SELL, got {sides}"
    b = FakeBroker([])
    with sandbox(b, "11:00") as (mod, root):
        seed(root, candidates=cands)
        (root / "data/live").mkdir(parents=True)
        (root / "data/live/state.json").write_text(json.dumps({"positions": {}, "trades": [], "daily_pnl": -900.0, "trading_day": "2025-12-31"}))
        run(mod)
        assert [o["transaction_type"] for o in b.orders] == ["BUY"], "yesterday's loss must not block today"


def test_eod_window_closes_positions_early_and_blocks_new_entries():
    b = FakeBroker([pos(ltp=100.1)])
    with sandbox(b, "15:14") as (mod, root):
        seed(root)
        run(mod)
        assert b.orders == [], "before the exit window nothing should be sold"
    cands = [{"symbol": "BB", "price": 50.0, "security_id": "22"}]
    b = FakeBroker([pos(ltp=100.1)])
    with sandbox(b, "15:20") as (mod, root):
        seed(root, candidates=cands)
        run(mod)
        assert [o["transaction_type"] for o in b.orders] == ["SELL"], "exit window: sell, and no new BUY"


def test_only_intraday_positions_are_managed():
    b = FakeBroker([pos(ltp=110.0, product="CNC"), pos("B", sec="12", ltp=110.0, product="INTRADAY")])
    with sandbox(b, "11:00") as (mod, root):
        seed(root)
        run(mod)
        assert [(o["transaction_type"], o["security_id"]) for o in b.orders] == [("SELL", "12")], "a CNC/delivery position must never be auto-sold"


def test_no_ai_means_deterministic_entry_but_ai_watch_blocks():
    b = FakeBroker([], funds=10000.0)
    with sandbox(b, "11:00") as (mod, root):
        seed(root, candidates=[{"symbol": "BB", "price": 50.0, "security_id": "22", "ai_status": "AI_UNAVAILABLE", "verdict": None}])
        run(mod)
        assert [o["transaction_type"] for o in b.orders] == ["BUY"], "no AI reachable -> bot still trades on its own rules"
    b = FakeBroker([], funds=10000.0)
    with sandbox(b, "11:00") as (mod, root):
        seed(root, candidates=[{"symbol": "BB", "price": 50.0, "security_id": "22", "ai_status": "COMPLETE", "verdict": "WATCH"}])
        run(mod)
        assert b.orders == [], "AI available and not SUPPORT -> no real-money entry"


def test_public_flag_is_truthful():
    b = FakeBroker([])
    with sandbox(b, "11:00") as (mod, root):
        seed(root)
        run(mod)
        assert json.loads((root / "public/data/live_state.json").read_text())["live_orders_enabled"] is True
    with sandbox(b, "11:00", LIVE_KILL_SWITCH="1") as (mod, root):
        seed(root)
        run(mod)
        assert json.loads((root / "public/data/live_state.json").read_text())["live_orders_enabled"] is False


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    for t in TESTS:
        t()
        print(f"  ok  {t.__name__}")
    print("LIVE EXIT SELF-TEST: PASS")
