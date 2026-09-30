#!/usr/bin/env python3
"""Generate a browser-safe runtime health snapshot for MyTradeAnalysis.

No secret values are written. Telegram credentials are checked server-side
with Telegram getMe; Dhan/OpenAI/Anthropic operational state is derived from
the already-published paper-cycle evidence.
"""
from __future__ import annotations
import json, os, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

OUT=Path("public/data/runtime_status.json")
SNAPSHOT=Path("public/data/market_snapshot.json")
COUNCIL=Path("public/data/ai_research_council.json")

LIVE={"LIVE_MARKET_DATA","LIVE_MARKET_DATA_NSE","LIVE_MARKET_DATA_NSE_PROXY","LIVE_MARKET_DATA_FALLBACK"}

def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def load(path):
    try:
        value=json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value,dict) else {}
    except Exception:
        return {}

def telegram_status():
    token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat=(os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        return {"status":"NOT_CONFIGURED","label":"Not configured","detail":"Required GitHub Actions secrets are missing."}
    try:
        req=urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getMe",
            headers={"Accept":"application/json","User-Agent":"MyTradeAnalysis-health-check"},
        )
        with urllib.request.urlopen(req,timeout=10) as response:
            payload=json.loads(response.read().decode("utf-8","replace"))
        if payload.get("ok") is not True:
            return {"status":"ERROR","label":"Configured but rejected","detail":"Telegram API rejected the configured bot token."}
        chat_req=urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getChat?chat_id={urllib.parse.quote(chat,safe='')}",
            headers={"Accept":"application/json","User-Agent":"MyTradeAnalysis-health-check"},
        )
        with urllib.request.urlopen(chat_req,timeout=10) as chat_response:
            chat_payload=json.loads(chat_response.read().decode("utf-8","replace"))
        if chat_payload.get("ok") is True:
            return {"status":"READY","label":"Configured & reachable","detail":"Telegram bot token and target chat were verified server-side."}
        return {"status":"ERROR","label":"Token works; chat rejected","detail":"Telegram bot token is valid but the configured chat ID could not be verified."}
    except Exception as exc:
        return {"status":"ERROR","label":"Configured but unreachable","detail":f"Telegram API health check failed: {type(exc).__name__}."}

def main():
    snapshot=load(SNAPSHOT)
    council=load(COUNCIL)
    source=snapshot.get("source") or "Unknown"

    if snapshot.get("status") in LIVE and "Dhan" in source:
        dhan={"status":"READY","label":"Dhan feed ready","detail":"Latest market snapshot was collected from Dhan."}
    elif snapshot.get("reason",{}).get("dhan_error"):
        dhan={"status":"UNAVAILABLE","label":"Dhan feed unavailable","detail":"Latest paper cycle could not authenticate to Dhan; fallback data is explicitly labelled."}
    else:
        dhan={"status":"UNKNOWN","label":"Dhan status unknown","detail":"No verified Dhan market-feed result is published."}

    def ai(provider):
        cfg=(council.get("config") or {}).get(provider) or {}
        if not cfg.get("api_key_configured"):
            return {"status":"NOT_CONFIGURED","label":"Not configured","detail":f"{provider.title()} API key is not configured for the council."}
        status=council.get("status")
        errors=council.get("errors") or {}
        err=errors.get(provider)
        if err:
            return {"status":"UNAVAILABLE","label":"Configured but unavailable","detail":str(err)[:180]}
        if status in ("COMPLETE","READY"):
            return {"status":"READY","label":"Configured & participating","detail":f"{provider.title()} completed the current council run."}
        return {"status":"CONFIGURED","label":"Configured; council waiting","detail":f"{provider.title()} is configured; current council status is {status or 'UNKNOWN'}."}

    result={
        "schema_version":"1.0",
        "generated_at":now(),
        "telegram":telegram_status(),
        "dhan":dhan,
        "openai":ai("openai"),
        "anthropic":ai("anthropic"),
        "paper_only":True,
        "secrets_exposed":False,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({k:v.get("status") for k,v in result.items() if isinstance(v,dict)}))
if __name__=="__main__":
    raise SystemExit(main())
