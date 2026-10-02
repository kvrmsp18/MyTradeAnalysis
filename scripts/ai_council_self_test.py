#!/usr/bin/env python3
"""Offline provider-agnostic AI council acceptance tests."""
from ai_clients import classify,development_classification,resolve_advisory

def main():
    assert classify("# CLASSIFICATION: SUPPORTS_REVIEW")=="SUPPORTS_REVIEW"
    assert classify("**CLASSIFICATION:** WATCH_ONLY")=="WATCH_ONLY"
    assert classify("- CLASSIFICATION: NO_SUPPORT")=="NO_SUPPORT"
    assert development_classification("notes\nDEVELOPMENT_CLASSIFICATION: PASS")=="PASS"
    assert development_classification("PASSWORD contains PASS") is None

    a=resolve_advisory("", "CLASSIFICATION: SUPPORTS_REVIEW\nreview")
    assert a["status"]=="DEGRADED_ONE_AI" and a["working_provider"]=="Anthropic"
    o=resolve_advisory("CLASSIFICATION: WATCH_ONLY\nreview", "")
    assert o["status"]=="DEGRADED_ONE_AI" and o["working_provider"]=="OpenAI"
    n=resolve_advisory("", "")
    assert n["status"]=="AI_UNAVAILABLE" and n["classification"] is None
    d=resolve_advisory("CLASSIFICATION: SUPPORTS_REVIEW","CLASSIFICATION: NO_SUPPORT")
    assert d["status"]=="DISAGREEMENT" and d["classification"]=="HOLD_FOR_REVIEW"
    c=resolve_advisory("CLASSIFICATION: WATCH_ONLY","CLASSIFICATION: WATCH_ONLY")
    assert c["status"]=="COMPLETE" and c["classification"]=="WATCH_ONLY"
    print("AI COUNCIL SELF-TEST: PASS")
    print("Parser: PASS | Anthropic-only: PASS | OpenAI-only: PASS | None: PASS | Disagreement hold: PASS | Agreement: PASS")
if __name__=="__main__": main()
