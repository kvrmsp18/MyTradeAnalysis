#!/usr/bin/env python3
"""Offline tests for the dynamic universe, learning loop, per-share AI verdicts and EOD summary.
No network, no API keys. Every scenario runs in a throw-away working directory.
"""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
def load_module(name: str):
 spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
 mod = importlib.util.module_from_spec(spec)
 spec.loader.exec_module(mod)
 return mod
@contextlib.contextmanager
def sandbox(**env):
 saved, cwd = dict(os.environ), os.getcwd()
 with tempfile.TemporaryDirectory() as td:
 try:
 for key in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN", "LEARNING_ENABLED", "PAPER_REVIEW_SCORE", 
"SCRAP_REVIEW_CUTOFF",
 "UNIVERSE_TOP_N", "PAPER_ANALYSIS_BUDGET", "AI_COUNCIL_FORCE"):
 os.environ.pop(key, None)
 os.environ.update({k: str(v) for k, v in env.items()})
 os.chdir(td)
 yield Path(td)
 finally:
 os.chdir(cwd)
 os.environ.clear()
 os.environ.update(saved)
def quiet(fn, *a, **k):
 with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
 return fn(*a, **k)
def master_csv(names, extra=()):
 head = 
"SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_TRADING_SYMBOL,SEM_SERIES\n"
 rows = [f"NSE,E,{1000 + i},EQUITY,{n},EQ" for i, n in enumerate(names)]
 rows += list(extra)
 return head + "\n".join(rows) + "\n"
def synth_names(n): # deliberately meaningless names: ranking must not care what a share is called
 return [f"ZZ{i:04d}" for i in range(n)]
def dhan_payload(names, last_trade="02/10/2026 11:00:00"):
 data = {}
 for i, n in enumerate(names):
 prev = 100.0 + (i % 50)
 move = ((i * 37) % 21 - 10) / 2.0 # -5.0 .. +5.0 %
<PARSED TEXT FOR PAGE: 50 / 56>
 data[str(1000 + i)] = {
 "last_price": round(prev * (1 + move / 100), 2), "volume": 10_000 + (i * 7919) % 900_000,
 "last_trade_time": last_trade,
 "ohlc": {"open": prev, "high": round(prev * 1.03, 2), "low": round(prev * 0.98, 2), "close": 
prev},
 }
 return {"data": {"NSE_EQ": data}, "status": "success"}
# ------------------------------------------------------------------ universe
def test_no_hardcoded_share_list_anywhere():
 quoted_run = re.compile(r'(?:["\'][A-Z][A-Z0-9&\-]{1,14}["\']\s*,\s*){9,}["\'][A-Z][A-Z0-9&\-]{1,14}
["\']')
 offenders = []
 for path in SCRIPTS.glob("*.py"):
 if path.name.endswith("_test.py"):
 continue
 if quoted_run.search(path.read_text(encoding="utf-8")):
 offenders.append(path.name)
 assert not offenders, f"hard-coded share list in {offenders}"
 assert "SYMBOLS" not in (SCRIPTS / "market_snapshot.py").read_text(encoding="utf-8")
def test_parse_master_keeps_only_nse_equity_series_eq():
 u = load_module("universe")
 text = master_csv(["AAA", "BBB"], extra=[
 "NSE,E,9001,EQUITY,CCC,BE", "BSE,E,9002,EQUITY,DDD,EQ", "NSE,D,9003,FUTSTK,EEE,",
 "NSE,E,9004,INDEX,NIFTY,EQ", "NSE,E,9005,EQUITY,FFF,EQ"])
 ids = u.parse_master(text)
 assert set(ids) == {"AAA", "BBB", "FFF"}, ids
def test_ranking_is_generic_deterministic_and_bounded():
 u = load_module("universe")
 names = synth_names(300)
 rows = []
 for r in dhan_payload(names)["data"]["NSE_EQ"].items():
 pass
 from market_snapshot import normalise_dhan # noqa: F401 (import check only)
 ms = load_module("market_snapshot")
 rows = ms.normalise_dhan(dhan_payload(names), {n: str(1000 + i) for i, n in enumerate(names)})
 sel1, st1 = u.select_candidates(rows, top_n=40, max_price=1000)
 sel2, _ = u.select_candidates(list(reversed(rows)), top_n=40, max_price=1000)
 assert [r["symbol"] for r in sel1] == [r["symbol"] for r in sel2], "ranking depends on input order"
 assert len(sel1) == 40 and st1["scanned"] == 300 and st1["liquid"] < st1["eligible"]
 assert all(r["price"] <= 1000 and r["price"] >= u.MIN_PRICE for r in sel1)
 # momentum matters: the best selected share changes more than the median scanned share
 med = sorted(r["change"] for r in rows)[len(rows) // 2]
 assert max(r["change"] for r in sel1) > med
 # liquidity floor: nothing from the bottom half by turnover
 turn = sorted(rows, key=lambda r: r["price"] * (r["volume"] or 0))
 bottom = {r["symbol"] for r in turn[: len(turn) // 2 - 1]}
 assert not bottom & {r["symbol"] for r in sel1}
def test_dhan_full_market_scan_end_to_end():
 ms = load_module("market_snapshot")
 names = synth_names(700)
 with sandbox(DHAN_CLIENT_ID="c", DHAN_ACCESS_TOKEN="t", PAPER_ANALYSIS_BUDGET="1000") as root:
 calls = []
 def fake_fetch(url, headers=None, body=None, timeout=25):
 calls.append(url)
 if url.endswith("api-scrip-master.csv"):
 return master_csv(names).encode()
 if "marketfeed/quote" in url:
 ids = json.loads(body)["NSE_EQ"]
 assert len(ids) == 700 and len(ids) <= ms.BATCH
 return json.dumps(dhan_payload(names)).encode()
 raise RuntimeError("offline")
 ms.fetch, ms.time.sleep = fake_fetch, lambda s: None
<PARSED TEXT FOR PAGE: 51 / 56>
 quiet(ms.main)
 snap = json.loads((root / "public/data/market_snapshot.json").read_text())
 assert snap["status"] == "LIVE_MARKET_DATA", snap["status"]
 assert snap["universe"]["mode"] == "DYNAMIC_FULL_NSE_SCAN" and snap["universe"]["scanned"] == 700
 assert 0 < len(snap["stocks"]) <= 60 and all(s["symbol"].startswith("ZZ") for s in snap["stocks"])
 assert snap["regime"]["observed"] == 700, "regime must be whole-market breadth"
 # freshness: provider quote time (11:00 IST == 05:30Z), NOT 'now'
 assert snap["data_as_of"] == "2026-10-02T05:30:00Z", snap["data_as_of"]
 saved = json.loads((root / "data/universe/last_selected.json").read_text())
 assert snap["data_as_of_basis"] == "PROVIDER_QUOTE_TIME"
 assert saved["symbols"] == [s["symbol"] for s in snap["stocks"]]
 assert (root / "data/universe/nse_equity.json").exists()
def test_fallback_uses_carried_discovery_never_a_typed_list():
 ms, u = load_module("market_snapshot"), load_module("universe")
 with sandbox() as root:
 u.save_selected(["QQ1", "QQ2", "QQ3"], {}, "DHAN_FULL_MARKET_SCAN")
 ms.fetch = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
 seen = {}
 def nse_blocked(symbols): raise RuntimeError("NSE India access blocked (HTTP 403)")
 def yahoo(symbols):
 seen["symbols"] = list(symbols)
 return [{"symbol": s, "price": 50.0, "change": 1.0, "quote_time": "2026-10-02T05:00:00Z"} for s 
in symbols], []
 ms.nse_fallback, ms.nse_proxy_fallback, ms.yahoo_fallback = nse_blocked, nse_blocked, yahoo
 quiet(ms.main)
 snap = json.loads((root / "public/data/market_snapshot.json").read_text())
 assert snap["status"] == "LIVE_MARKET_DATA_FALLBACK" and snap["universe"]["mode"] == 
"CARRIED_DYNAMIC"
 assert seen["symbols"] == ["QQ1", "QQ2", "QQ3"] and snap["data_as_of"] == "2026-10-02T05:00:00Z"
def test_no_discovery_means_no_data_and_no_trading():
 ms = load_module("market_snapshot")
 with sandbox() as root:
 ms.fetch = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
 quiet(ms.main)
 snap = json.loads((root / "public/data/market_snapshot.json").read_text())
 assert snap["status"] == "DATA_UNAVAILABLE" and snap["stocks"] == []
def test_bhavcopy_bootstrap_discovers_universe_without_dhan():
 ms = load_module("market_snapshot")
 names = synth_names(600)
 header = "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, 
AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS\n"
 body = "".join(f"{n}, EQ, 01-Oct-2026, 100, 101, {103 + i % 5}, 99, 102, {100 + (i % 9)}, 101, {50000 + i
* 13}, 10\n" for i, n in enumerate(names))
 with sandbox() as root:
 def fetch(url, headers=None, body_=None, timeout=25):
 if "sec_bhavdata_full" in url:
 return (header + body).encode()
 raise RuntimeError("offline")
 ms.fetch = fetch
 ms.nse_fallback = ms.nse_proxy_fallback = lambda s: (_ for _ in ()).throw(RuntimeError("blocked"))
 ms.yahoo_fallback = lambda s: ([{"symbol": x, "price": 100.0, "change": 0.5, "quote_time": None} for 
x in s], [])
 quiet(ms.main)
 snap = json.loads((root / "public/data/market_snapshot.json").read_text())
 assert snap["universe"]["mode"] == "BHAVCOPY_PREVIOUS_SESSION" and 0 < len(snap["stocks"]) <= 60
 assert snap["data_as_of_basis"] == "FETCH_TIME_NO_PROVIDER_TIMESTAMP" and snap["data_as_of"] # 
labelled, not silently None
# ------------------------------------------------------------------ learning loop
PATTERN = lambda reason, n: {"pattern": reason, "distinct_symbols": n, "occurrences": n * 4} # noqa: E731
<PARSED TEXT FOR PAGE: 52 / 56>
def test_learning_adjusts_only_general_parameters_with_cross_symbol_evidence():
 lp = load_module("learning_policy")
 with sandbox():
 base = lp.effective()
 assert (base["scrap_review_cutoff"], base["review_score"], base["universe_top_n"]) == (70.0, 65.0, 
60)
 out = lp.apply_learning("2026-10-02", [PATTERN("SCRAP_WATCH_ONLY", 5), 
PATTERN("NOT_IN_PAPER_CANDIDATE_UNIVERSE_NO_RECONSTRUCTED_SETUP", 4),
 PATTERN("SCRAP_BELOW_REVIEW_THRESHOLD", 9), 
PATTERN("EXECUTION_INSUFFICIENT_CAPITAL", 6)],
 {"realized_pnl": 12.0, "stop_loss_exits": 0})
 eff = lp.effective(out["policy"])
 assert (eff["scrap_review_cutoff"], eff["review_score"], eff["universe_top_n"]) == (69.0, 64.0, 65), 
eff
 params = {c["parameter"] for c in out["changes"]}
 assert params == {"scrap_review_cutoff", "review_score", "universe_top_n"}
 assert all("symbol" not in json.dumps(c["evidence"]).lower().replace("distinct_symbols", "") for c in
out["changes"])
 # report-only reasons never move anything
 assert any(s.get("pattern") == "SCRAP_BELOW_REVIEW_THRESHOLD" for s in out["skipped"])
 assert any(s.get("pattern") == "EXECUTION_INSUFFICIENT_CAPITAL" for s in out["skipped"])
def test_learning_needs_3_symbols_blocks_after_loss_and_tightens():
 lp = load_module("learning_policy")
 with sandbox():
 weak = lp.apply_learning("d1", [PATTERN("SCRAP_WATCH_ONLY", 2)], {"realized_pnl": 5})
 assert weak["changes"] == []
 loss = lp.apply_learning("d2", [PATTERN("SCRAP_WATCH_ONLY", 8)], {"realized_pnl": -30, 
"stop_loss_exits": 1})
 assert loss["changes"] == [] and any("loosening blocked" in s.get("reason", "") for s in 
loss["skipped"])
 tight = lp.apply_learning("d3", [], {"realized_pnl": -40, "stop_loss_exits": 3})
 eff = lp.effective(tight["policy"])
 assert eff["scrap_review_cutoff"] == 71.0 and eff["review_score"] == 66.0
def test_learning_idempotent_bounded_and_reversible():
 lp = load_module("learning_policy")
 with sandbox():
 policy = lp.load()
 for day in range(1, 40): # relentless pressure to loosen
 policy = lp.apply_learning(f"day{day}", [PATTERN("SCRAP_WATCH_ONLY", 9), 
PATTERN("NOT_IN_PAPER_CANDIDATE_UNIVERSE_NO_RECONSTRUCTED_SETUP", 9)],
 {"realized_pnl": 1}, policy)["policy"]
 eff = lp.effective(policy)
 assert eff["scrap_review_cutoff"] >= 60 and eff["review_score"] >= 55 and eff["universe_top_n"] <= 
100, eff
 assert eff["scrap_review_cutoff"] >= 70 * 0.85 - 1e-9 and eff["review_score"] >= 65 * 0.85 - 1e-9, 
"15% drift cap broken"
 again = lp.apply_learning("day39", [PATTERN("SCRAP_WATCH_ONLY", 9)], {"realized_pnl": 1}, policy)
 assert again["changes"] == [], "same day applied twice"
 os.environ["LEARNING_ENABLED"] = "0"
 off = lp.effective(policy)
 assert (off["scrap_review_cutoff"], off["review_score"], off["universe_top_n"]) == (70.0, 65.0, 60) 
and off["source"] == "base"
 os.environ.pop("LEARNING_ENABLED")
 lp.save(policy)
 assert len(json.loads(lp.POLICY_PATH.read_text())["log"]) <= lp.LOG_KEEP
def test_env_base_outside_default_bounds_is_respected():
 lp = load_module("learning_policy")
 with sandbox(PAPER_REVIEW_SCORE="90"):
 assert lp.effective()["review_score"] == 90.0
def test_eod_report_applies_learning_and_next_session_uses_it():
 eod, lp = load_module("eod_learning"), load_module("learning_policy")
 with sandbox() as root:
 report = {"general_patterns": [PATTERN("SCRAP_WATCH_ONLY", 6)]}
 (root / "data/paper").mkdir(parents=True)
<PARSED TEXT FOR PAGE: 53 / 56>
 (root / "data/paper/state.json").write_text(json.dumps({"trades": [
 {"side": "SELL", "symbol": "X", "pnl": 7.5, "reason": "TARGET", "timestamp": "2026-10-
02T06:00:00Z"}]}))
 eod.apply_and_save(report, "2026-10-02")
 assert report["learning"]["changes"] and report["learning"]["day_stats"]["realized_pnl"] == 7.5
 assert lp.effective()["scrap_review_cutoff"] == 69.0
 scrap = load_module("scrap_analysis")
 assert scrap.REVIEW_CUTOFF == 69.0, "SCRAP must pick up the learned cutoff"
# ------------------------------------------------------------------ per-share AI + deterministic path
def _cycle_inputs(root, council):
 (root / "public/data").mkdir(parents=True, exist_ok=True)
 stocks, scrap = [], []
 for sym in ("AA", "BB", "CC"):
 stocks.append({"symbol": sym, "price": 102.0, "change": 3.0, "open": 100.0, "high": 103.0, "low": 
100.0, "prev_close": 99.0,
 "volume": 500000, "security_id": "1"})
 scrap.append({"symbol": sym, "status": "OK", "score": 85, "action": "REVIEW", "indicators": {}})
 (root / "public/data/market_snapshot.json").write_text(json.dumps(
 {"status": "LIVE_MARKET_DATA", "stocks": stocks, "regime": {"label": "BULLISH", "breadth": 70.0, 
"confidence": 40.0, "observed": 900}}))
 (root / "public/data/scrap_analysis.json").write_text(json.dumps({"status": "LIVE_TECHNICAL_DATA", 
"stocks": scrap}))
 if council is not None:
 (root / "public/data/ai_research_council.json").write_text(json.dumps(council))
def _decisions(root):
 ledger = json.loads(next((root / "data/ledger").glob("*/*.json")).read_text())
 return {c["symbol"]: c for c in ledger["candidates"]}, ledger
def test_per_share_ai_verdicts_shape_decisions_and_market_veto_wins():
 def run(council):
 with sandbox() as root:
 _cycle_inputs(root, council)
 quiet(load_module("paper_cycle").main)
 return _decisions(root)
 good = {"status": "COMPLETE", "consensus": {"classification": "SUPPORTS_REVIEW"},
 "candidate_verdicts": {"AA": {"verdict": "SUPPORT"}, "BB": {"verdict": "AVOID"}, "CC": 
{"verdict": "WATCH"}}}
 d, ledger = run(good)
 assert (d["AA"]["decision"], d["BB"]["decision"], d["CC"]["decision"]) == ("REVIEW", "WATCH", "WATCH")
 assert d["BB"]["ai_council"]["symbol_verdict"] == "AVOID" and ledger["market_regime"]["basis"] == 
"whole_market_scan"
 veto = {"status": "COMPLETE", "consensus": {"classification": "NO_SUPPORT"}, "candidate_verdicts": {"AA":
{"verdict": "SUPPORT"}}}
 d, _ = run(veto)
 assert d["AA"]["decision"] == "WATCH", "a per-share SUPPORT must not override a market-wide NO_SUPPORT"
 d, _ = run({"status": "AI_UNAVAILABLE", "consensus": {"classification": None}})
 assert {x["decision"] for x in d.values()} == {"REVIEW"}, "no AI -> deterministic analysis still produces
candidates"
 d, _ = run(None)
 assert {x["decision"] for x in d.values()} == {"REVIEW"}
def test_council_collects_verdicts_and_survives_missing_market_data():
 rc = load_module("ai_research_council")
 with sandbox(AI_COUNCIL_FORCE="1") as root:
 (root / "public/data").mkdir(parents=True)
 (root / "public/data/market_snapshot.json").write_text(json.dumps({"status": "DATA_UNAVAILABLE", 
"stocks": []}))
 assert quiet(rc.main) == 0, "council crashed on unavailable market data (UnboundLocalError 
regression)"
 assert json.loads(rc.OUT.read_text())["status"] == "AI_UNAVAILABLE"
 with sandbox(AI_COUNCIL_FORCE="1") as root:
 _cycle_inputs(root, None)
 reply = "CLASSIFICATION: SUPPORTS_REVIEW\nAA: SUPPORT\nBB: AVOID\nCC: WATCH\nGeneral commentary."
 rc.call_openai = lambda prompt, evidence, max_output_tokens=0: ("", "OpenAI HTTP 429: 
credit_balance_exhausted")
<PARSED TEXT FOR PAGE: 54 / 56>
 rc.call_anthropic = lambda prompt, evidence, max_output_tokens=0: (reply, None)
 quiet(rc.main)
 out = json.loads(rc.OUT.read_text())
 assert out["status"] == "DEGRADED_ONE_AI" and out["working_provider"] == "Anthropic"
 assert {k: v["verdict"] for k, v in out["candidate_verdicts"].items()} == {"AA": "SUPPORT", "BB": 
"AVOID", "CC": "WATCH"}
 assert out["execution_authorized"] is False and out["provider_backoff_until"].get("openai")
# ------------------------------------------------------------------ executor honours learned threshold; EOD 
summary
def test_executor_uses_learned_review_score():
 import runpy
 def run(delta):
 with sandbox(PAPER_STARTING_CAPITAL="10000", PAPER_ANALYSIS_BUDGET="1000", 
PAPER_ENGINE_TEST_TIME_IST="2026-01-01 10:00") as root:
 (root / "public/data").mkdir(parents=True)
 fresh = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
 (root / "public/data/market_snapshot.json").write_text(json.dumps(
 {"status": "LIVE_MARKET_DATA", "data_as_of": fresh, "stocks": [{"symbol": "AA", "price": 
50.0}]}))
 led = root / "data/ledger/2026-01-01"
 led.mkdir(parents=True)
 (led / "000001.json").write_text(json.dumps({"mode": "PAPER", "candidates": [{
 "symbol": "AA", "ranking": 1, "decision": "REVIEW", "features": {"score": 63}, 
"scrap_result": {"score": 75}, "quote": {"price": 50.0}}]}))
 if delta:
 (root / "data/learning").mkdir(parents=True)
 (root / "data/learning/policy.json").write_text(json.dumps({"deltas": {"review_score": 
delta}, "log": []}))
 try:
 quiet(runpy.run_path, str(SCRIPTS / "paper_executor.py"), run_name="__main__")
 except SystemExit:
 pass
 return json.loads((root / "data/paper/state.json").read_text())["positions"]
 assert run(0) == {}, "score 63 < 65 must not buy"
 assert "AA" in run(-3), "learned threshold 62 should allow the buy"
def test_eod_summary_lists_bought_sold_and_total_pnl():
 es = load_module("eod_trade_summary")
 with sandbox() as root:
 (root / "data/paper").mkdir(parents=True)
 (root / "public/data").mkdir(parents=True)
 (root / "data/paper/state.json").write_text(json.dumps({
 "positions": {"OPEN1": {"quantity": 2, "entry_price": 100.0}},
 "trades": [
 {"side": "BUY", "symbol": "AA", "quantity": 2, "price": 100.0, "timestamp": "2026-10-
02T04:00:00Z"},
 {"side": "SELL", "symbol": "AA", "quantity": 2, "price": 102.0, "entry_price": 100.0, "pnl": 
4.0, "reason": "TARGET", "timestamp": "2026-10-02T05:00:00Z"},
 {"side": "BUY", "symbol": "BB", "quantity": 3, "price": 50.0, "timestamp": "2026-10-
02T05:10:00Z"},
 {"side": "SELL", "symbol": "BB", "quantity": 3, "price": 49.5, "entry_price": 50.0, "pnl": 
-1.5, "reason": "STOP_LOSS", "timestamp": "2026-10-02T06:00:00Z"},
 {"side": "SELL", "symbol": "OLD", "quantity": 1, "price": 9.0, "entry_price": 8.0, "pnl": 
1.0, "reason": "TARGET", "timestamp": "2026-10-01T06:00:00Z"}]}))
 (root / "public/data/market_snapshot.json").write_text(json.dumps({"stocks": [{"symbol": "OPEN1", 
"price": 101.0}]}))
 (root / "public/data/eod_report.json").write_text(json.dumps({"learning": {"changes": [{"parameter": 
"review_score", "from": 65, "to": 64}]}}))
 s = es.build("2026-10-02")
 assert [b["symbol"] for b in s["buys"]] == ["AA", "BB"] and [x["symbol"] for x in s["sells"]] == 
["AA", "BB"]
 assert s["realized_pnl"] == 2.5 and s["unrealized_pnl"] == 2.0 and s["total_pnl"] == 4.5 and 
(s["wins"], s["losses"]) == (1, 1)
 msg = es.text(s)
 for needle in ("BOUGHT (2)", "SOLD (2)", "AA x2", "STOP_LOSS", "TOTAL P/L TODAY: +Rs.4.50", 
"review_score: 65 -> 64", "STILL OPEN"):
 assert needle in msg, (needle, msg)
 assert "OLD x1" not in msg, "yesterday's trade leaked into today's report"
<PARSED TEXT FOR PAGE: 55 / 56>
def test_eod_summary_stays_under_telegram_limit_and_keeps_totals():
 es = load_module("eod_trade_summary")
 trades = []
 for i in range(120):
 trades.append({"side": "BUY", "symbol": f"S{i:03d}", "quantity": 1, "price": 10.0, "timestamp": 
"2026-10-02T04:00:00Z"})
 trades.append({"side": "SELL", "symbol": f"S{i:03d}", "quantity": 1, "price": 10.1, "entry_price": 
10.0, "pnl": 0.1,
 "reason": "TARGET", "timestamp": "2026-10-02T05:00:00Z"})
 with sandbox() as root:
 (root / "data/paper").mkdir(parents=True)
 (root / "data/paper/state.json").write_text(json.dumps({"positions": {}, "trades": trades}))
 msg = es.text(es.build("2026-10-02"))
 assert len(msg) < 4000 and "TOTAL P/L TODAY: +Rs.12.00" in msg and "+105 more" in msg, (len(msg), 
msg[-300:])
TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
if __name__ == "__main__":
 for t in TESTS:
 t()
 print(f" ok {t.__name__}")
 print("DYNAMIC BOT SELF-TEST: PASS")