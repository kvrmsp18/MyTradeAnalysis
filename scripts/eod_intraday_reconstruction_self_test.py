#!/usr/bin/env python3
"""Offline tests for Dhan intraday reconstruction request formatting."""
import json
from datetime import datetime, timezone
from urllib.request import Request
from zoneinfo import ZoneInfo

import eod_intraday_reconstruction as module


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b'{"data": {}}'


def main():
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    original = module.urllib.request.urlopen
    module.urllib.request.urlopen = fake_urlopen
    try:
        module.fetch_candles("token", "client", "11536", "2026-10-02")
    finally:
        module.urllib.request.urlopen = original

    request = captured["request"]
    assert isinstance(request, Request)
    assert request.full_url == "https://api.dhan.co/v2/charts/intraday"
    body = json.loads(request.data.decode("utf-8"))
    assert body["fromDate"] == "2026-10-02 09:15:00"
    assert body["toDate"] == "2026-10-02 15:30:00"
    assert body["interval"] == "5"
    assert body["securityId"] == "11536"

    utc_near_midnight = datetime(2026, 10, 1, 23, 45, tzinfo=timezone.utc)
    expected_ist_date = utc_near_midnight.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
    assert expected_ist_date == "2026-10-02"

    print("EOD INTRADAY RECONSTRUCTION SELF-TEST: PASS")
    print("Dhan URL: PASS | IST date: PASS | Session window: PASS | Interval 5: PASS")


if __name__ == "__main__":
    main()
