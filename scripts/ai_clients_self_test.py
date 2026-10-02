#!/usr/bin/env python3
"""Offline tests for AI provider 429 credit/quota/billing handling."""
import urllib.error

import ai_clients as module


def main():
    calls = []
    sleeps = []

    class BodyHTTPError(urllib.error.HTTPError):
        def read(self):
            return b'{"error":"insufficient_quota","message":"No credits remaining; check billing."}'

    def fake_urlopen(request, timeout=0):
        calls.append(request)
        raise BodyHTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    original_urlopen = module.urllib.request.urlopen
    original_sleep = module.time.sleep
    module.urllib.request.urlopen = fake_urlopen
    module.time.sleep = lambda seconds: sleeps.append(seconds)
    try:
        try:
            module.request_json(
                "https://example.test",
                {},
                {"test": True},
                "OpenAI",
                retries=3,
            )
        except RuntimeError as exc:
            assert "HTTP 429" in str(exc)
            assert "insufficient_quota" in str(exc)
        else:
            raise AssertionError("Expected immediate RuntimeError for credit/quota 429")
    finally:
        module.urllib.request.urlopen = original_urlopen
        module.time.sleep = original_sleep

    assert len(calls) == 1
    assert sleeps == []

    print("AI CLIENTS SELF-TEST: PASS")
    print("429 credit/quota/billing: NON-RETRYABLE | Immediate failure: PASS")


if __name__ == "__main__":
    main()
