#!/usr/bin/env python3
"""Read Dhan available funds without ever placing an order.

Paper mode may use a documented minimum fallback for analysis when broker
funds cannot be read. Live mode is different: a fallback is NEVER acceptable.
The live executor independently re-reads broker funds immediately before
entry sizing so a stale or fabricated balance can never authorize a BUY.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


URL = "https://api.dhan.co/v2/fundlimit"


def find_available(value):
    if isinstance(value, dict):
        for key in (
            "availabelBalance",
            "availableBalance",
            "available_cash",
            "availableCash",
            "withdrawableBalance",
        ):
            raw = value.get(key)
            try:
                if raw is not None and float(raw) >= 0:
                    return float(raw)
            except (TypeError, ValueError):
                pass
        for child in value.values():
            found = find_available(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_available(child)
            if found is not None:
                return found
    return None


def set_env(key: str, value: str) -> None:
    env_file = os.getenv("GITHUB_ENV")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as handle:
            handle.write(f"{key}={value}
")


def set_paper_fallback(reason: str) -> int:
    set_env("PAPER_FUNDS_STATUS", "FALLBACK_MINIMUM")
    set_env("PAPER_AVAILABLE_CAPITAL", "1000.00")
    set_env("PAPER_ANALYSIS_BUDGET", "1000.00")
    set_env("LIVE_FUNDS_STATUS", "UNAVAILABLE")
    set_env("LIVE_AVAILABLE_CAPITAL", "0")
    print(f"PAPER_FUNDS_STATUS=FALLBACK_MINIMUM ({reason})")
    print("PAPER_ANALYSIS_BUDGET=1000.00")
    return 0


def main() -> int:
    token = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
    client = (os.getenv("DHAN_CLIENT_ID") or "").strip()

    if not token or not client:
        return set_paper_fallback("Dhan credentials missing")

    request = urllib.request.Request(
        URL,
        headers={
            "access-token": token,
            "client-id": client,
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        available = find_available(payload)
        if available is None:
            return set_paper_fallback("available balance missing")

        budget = max(1000.0, available)
        set_env("PAPER_FUNDS_STATUS", "READY")
        set_env("PAPER_AVAILABLE_CAPITAL", f"{available:.2f}")
        set_env("PAPER_ANALYSIS_BUDGET", f"{budget:.2f}")
        set_env("LIVE_FUNDS_STATUS", "READY")
        set_env("LIVE_AVAILABLE_CAPITAL", f"{available:.2f}")
        print("PAPER_FUNDS_STATUS=READY")
        print("PAPER_FUNDS_CHECK=PASS")
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return set_paper_fallback(type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
