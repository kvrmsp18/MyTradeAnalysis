#!/usr/bin/env python3
"""Dhan live-order adapter.

This module is the ONLY code path allowed to submit broker orders.
It is deliberately fail-closed:
- DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN and DHAN_API_KEY must be present.
- LIVE_TRADING_ENABLED must be exactly "1".
- LIVE_TRADING_CONFIRMATION must be exactly "I_UNDERSTAND_LIVE_ORDERS".
- Every order carries a client-generated idempotency reference.
- No credentials are ever written to logs or output.

The Dhan order API is called only from the server-side GitHub Actions runner.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

BASE_URL = "https://api.dhan.co/v2"
ORDERS_URL = BASE_URL + "/orders"
ORDER_DETAIL_URL = BASE_URL + "/orders/{order_id}"
POSITIONS_URL = BASE_URL + "/positions"


class LiveOrderBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class DhanConfig:
    client_id: str
    access_token: str
    api_key: str


def config_from_env() -> DhanConfig:
    client_id = (os.getenv("DHAN_CLIENT_ID") or "").strip()
    access_token = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
    api_key = (os.getenv("DHAN_API_KEY") or "").strip()
    if not client_id or not access_token or not api_key:
        raise LiveOrderBlocked("Dhan live credentials are incomplete; live orders are blocked.")
    if os.getenv("LIVE_TRADING_ENABLED") != "1":
        raise LiveOrderBlocked("LIVE_TRADING_ENABLED is not 1; live orders are blocked.")
    if os.getenv("LIVE_TRADING_CONFIRMATION") != "I_UNDERSTAND_LIVE_ORDERS":
        raise LiveOrderBlocked("Explicit live-order confirmation is missing; live orders are blocked.")
    return DhanConfig(client_id, access_token, api_key)


def _headers(cfg: DhanConfig) -> dict[str, str]:
    # Dhan's authenticated REST calls use the access-token/client-id headers.
    # DHAN_API_KEY is a required application-level readiness credential but is
    # intentionally not guessed into an undocumented HTTP header.
    return {
        "access-token": cfg.access_token,
        "client-id": cfg.client_id,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(method: str, url: str, cfg: DhanConfig, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers=_headers(cfg), method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"error": raw[:500]}
        raise RuntimeError(f"Dhan HTTP {exc.code}: {safe_error(data)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Dhan network error: {type(exc).__name__}") from exc


def safe_error(value: Any) -> str:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            low = str(key).lower()
            if any(secret in low for secret in ("token", "secret", "api_key", "apikey", "authorization")):
                continue
            clean[key] = item
        return json.dumps(clean, separators=(",", ":"))[:700]
    return str(value)[:700]


def submit_order(
    *,
    transaction_type: str,
    exchange_segment: str,
    security_id: str,
    quantity: int,
    product_type: str = "INTRADAY",
    order_type: str = "MARKET",
    price: float = 0.0,
    trigger_price: float = 0.0,
    validity: str = "DAY",
    tag: str,
) -> dict[str, Any]:
    cfg = config_from_env()
    if transaction_type not in {"BUY", "SELL"}:
        raise ValueError("transaction_type must be BUY or SELL")
    if exchange_segment != "NSE_EQ":
        raise ValueError("Only NSE_EQ cash orders are enabled")
    if int(quantity) <= 0:
        raise ValueError("quantity must be positive")
    if product_type != "INTRADAY":
        raise ValueError("Only INTRADAY product is enabled")
    if order_type not in {"MARKET", "LIMIT"}:
        raise ValueError("Only MARKET/LIMIT orders are enabled")
    if len(tag) > 30:
        tag = tag[:30]

    payload = {
        "dhanClientId": cfg.client_id,
        "transactionType": transaction_type,
        "exchangeSegment": exchange_segment,
        "productType": product_type,
        "orderType": order_type,
        "validity": validity,
        "securityId": str(security_id),
        "quantity": int(quantity),
        "disclosedQuantity": 0,
        "price": float(price) if order_type == "LIMIT" else 0,
        "triggerPrice": float(trigger_price) if order_type == "SL" else 0,
        "afterMarketOrder": False,
        "amoTime": "",
        "boProfitValue": 0,
        "boStopLossValue": 0,
        "drvExpiryDate": "",
        "drvOptionType": "",
        "drvStrikePrice": 0,
        "tag": tag,
    }
    response = _request("POST", ORDERS_URL, cfg, payload)
    if not isinstance(response, dict):
        raise RuntimeError("Dhan order response was not an object")
    return response


def order_detail(order_id: str) -> dict[str, Any]:
    cfg = config_from_env()
    response = _request("GET", ORDER_DETAIL_URL.format(order_id=str(order_id)), cfg)
    return response if isinstance(response, dict) else {"data": response}


def positions() -> list[dict[str, Any]]:
    cfg = config_from_env()
    response = _request("GET", POSITIONS_URL, cfg)
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        rows = response.get("data")
        return rows if isinstance(rows, list) else []
    return []


def is_fill_status(value: Any) -> bool:
    return str(value or "").upper() in {"TRADED", "PART_TRADED", "FILLED", "COMPLETE"}


if __name__ == "__main__":
    print("DHAN_LIVE_ORDER_ADAPTER=READY_FOR_CONFIGURED_RUNTIME")
