#!/usr/bin/env python3
"""Dhan live-order adapter.

This is the only code path allowed to submit broker orders.  It is fail-closed:
- DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN and DHAN_API_KEY must exist.
- TRADING_MODE must be LIVE.
- LIVE_KILL_SWITCH must not be 1.
- No browser code can reach this module.
- Every order is followed by broker-status capture for reconciliation.

The Dhan REST API is authenticated with access-token/client-id.  DHAN_API_KEY
is required as an application readiness credential, but is not guessed into an
undocumented HTTP header.
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
FUNDS_URL = BASE_URL + "/fundlimit"


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
    if os.getenv("TRADING_MODE", "PAPER").upper() != "LIVE":
        raise LiveOrderBlocked("TRADING_MODE is not LIVE; live orders are blocked.")
    if os.getenv("LIVE_KILL_SWITCH", "0") == "1":
        raise LiveOrderBlocked("LIVE_KILL_SWITCH=1; live orders are blocked.")

    return DhanConfig(client_id, access_token, api_key)


def _headers(cfg: DhanConfig) -> dict[str, str]:
    return {
        "access-token": cfg.access_token,
        "client-id": cfg.client_id,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(
    method: str,
    url: str,
    cfg: DhanConfig,
    payload: dict[str, Any] | None = None,
) -> Any:
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


def _find_available(value: Any) -> float | None:
    """Find a numeric available cash field without assuming one response shape."""
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
                number = float(raw)
                if number >= 0:
                    return number
            except (TypeError, ValueError):
                pass
        for child in value.values():
            found = _find_available(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_available(child)
            if found is not None:
                return found
    return None


def available_funds() -> float:
    """Fetch the current broker-available cash; fail closed if unreadable."""
    cfg = config_from_env()
    payload = _request("GET", FUNDS_URL, cfg)
    available = _find_available(payload)
    if available is None:
        raise RuntimeError("Dhan fundlimit response did not contain available cash")
    return float(available)


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
