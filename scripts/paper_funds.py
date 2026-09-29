#!/usr/bin/env python3
"""Check Dhan available funds for paper-entry gating.

This script never places an order and never publishes the actual broker
balance. It writes only a readiness flag and a private runtime value to
GITHUB_ENV when running inside GitHub Actions.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

URL = "https://api.dhan.co/v2/fundlimit"


def find_available(value):
    if isinstance(value, dict):
        for key in ("availabelBalance", "availableBalance", "available_cash", "availableCash", "withdrawableBalance"):
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
            handle.write(f"{key}={value}\n")


def main() -> int:
    token = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
    client = (os.getenv("DHAN_CLIENT_ID") or "").strip()

    if not token or not client:
        set_env("PAPER_FUNDS_STATUS", "UNAVAILABLE")
        print("PAPER_FUNDS_STATUS=UNAVAILABLE")
        return 0

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
            set_env("PAPER_FUNDS_STATUS", "UNAVAILABLE")
            print("PAPER_FUNDS_STATUS=UNAVAILABLE")
            return 0

        set_env("PAPER_FUNDS_STATUS", "READY")
        set_env("PAPER_AVAILABLE_CAPITAL", f"{available:.2f}")
        print("PAPER_FUNDS_STATUS=READY")
        print("PAPER_FUNDS_CHECK=PASS")
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        set_env("PAPER_FUNDS_STATUS", "UNAVAILABLE")
        print(f"PAPER_FUNDS_STATUS=UNAVAILABLE ({type(exc).__name__})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
