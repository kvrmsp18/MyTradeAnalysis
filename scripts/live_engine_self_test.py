#!/usr/bin/env python3
"""Offline safety tests for the live execution path. Never calls Dhan."""
from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dhan_order


def test_live_gate():
    keys = ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN", "DHAN_API_KEY", "TRADING_MODE", "LIVE_KILL_SWITCH")
    old = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    try:
        try:
            dhan_order.config_from_env()
        except dhan_order.LiveOrderBlocked:
            pass
        else:
            raise AssertionError("missing credentials must block")

        os.environ.update({
            "DHAN_CLIENT_ID": "test",
            "DHAN_ACCESS_TOKEN": "test",
            "DHAN_API_KEY": "test",
            "TRADING_MODE": "PAPER",
            "LIVE_KILL_SWITCH": "0",
        })
        try:
            dhan_order.config_from_env()
        except dhan_order.LiveOrderBlocked:
            pass
        else:
            raise AssertionError("PAPER mode must block live orders")

        os.environ["TRADING_MODE"] = "LIVE"
        os.environ["LIVE_KILL_SWITCH"] = "1"
        try:
            dhan_order.config_from_env()
        except dhan_order.LiveOrderBlocked:
            pass
        else:
            raise AssertionError("kill switch must block live orders")

        os.environ["LIVE_KILL_SWITCH"] = "0"
        cfg = dhan_order.config_from_env()
        assert cfg.client_id == "test"
    finally:
        for k, value in old.items():
            if value is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = value


def main():
    test_live_gate()
    print("LIVE ENGINE SAFETY SELF-TEST: PASS")


if __name__ == "__main__":
    main()
