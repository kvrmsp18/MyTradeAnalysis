#!/usr/bin/env python3
"""Run a non-executing OpenAI + Anthropic research council.

This module is deliberately limited to research discussion: evidence review,
contradictions, uncertainty and data gaps. It does not place orders and does not
produce an executable trade instruction. The deterministic paper engine remains
responsible for strategy and risk decisions.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT = Path("public/data/market_snapshot.json")
OUT = Path("public/data/ai_research_council.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def post(url: str, headers: dict[str, str], payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def openai_text(data: dict) -> str:
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []) if isinstance(item, dict) else []:
            if content.get("type") in ("output_text", "text") and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def anthropic_text(data: dict) -> str:
    return "\n".join(
        item.get("text", "") for item in data.get("content", [])
        if isinstance(item, dict) and item.get("type") == "text"
    ).strip()


def openai(prompt: str, evidence: dict) -> tuple[str, str | None]:
    key, model = os.getenv("OPENAI_API_KEY"), os.getenv("OPENAI_MODEL")
    if not key or not model:
        return "", "OpenAI not configured."
    try:
        data = post(
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {key}"},
            {"model": model, "input": prompt + "\n\nEVIDENCE:\n" + json.dumps(evidence, sort_keys=True), "store": False},
        )
        text = openai_text(data)
        return (text, None) if text else ("", "OpenAI returned no text.")
    except Exception as exc:
        return "", f"OpenAI unavailable: {exc}"


def anthropic(prompt: str, evidence: dict) -> tuple[str, str | None]:
    key, model = os.getenv("ANTHROPIC_API_KEY"), os.getenv("ANTHROPIC_MODEL")
    if not key or not model:
        return "", "Anthropic not configured."
    try:
        data = post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"model": model, "max_tokens": 1200, "messages": [{"role": "user", "content": prompt + "\n\nEVIDENCE:\n" + json.dumps(evidence, sort_keys=True)}]},
        )
        text = anthropic_text(data)
        return (text, None) if text else ("", "Anthropic returned no text.")
    except Exception as exc:
        return "", f"Anthropic unavailable: {exc}"


def write(data: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    if not SNAPSHOT.exists():
        write({"status": "UNAVAILABLE", "timestamp": utc_now(), "reason": "Market snapshot missing."})
        return 0

    evidence = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if evidence.get("status") != "LIVE_MARKET_DATA":
        write({"status": "UNAVAILABLE", "timestamp": utc_now(), "reason": "No verified market data available."})
        return 0

    analyst_prompt = (
        "You are an independent market-research analyst inside a paper-trading research system. "
        "Review only the supplied evidence. Do not invent prices, news, indicators or fundamentals. "
        "Produce: evidence summary, notable strengths/weaknesses, risks, contradictions, missing data, "
        "and questions another analyst should challenge. Do not issue an executable trade instruction."
    )
    openai_view, openai_error = openai(analyst_prompt, evidence)
    anthropic_view, anthropic_error = anthropic(analyst_prompt, evidence)

    if not openai_view or not anthropic_view:
        write({
            "status": "QUORUM_UNAVAILABLE",
            "timestamp": utc_now(),
            "paper_only": True,
            "openai": openai_view or None,
            "anthropic": anthropic_view or None,
            "errors": {"openai": openai_error, "anthropic": anthropic_error},
            "execution_authorized": False,
        })
        return 0

    critique_prompt = (
        "You are the second-pass reviewer in a two-model research council. Review the peer analysis below "
        "against the same evidence. Identify unsupported claims, missing evidence, contradictions and risk "
        "blind spots. Do not issue an executable trade instruction."
    )
    anthropic_critique, anthropic_critique_error = anthropic(
        critique_prompt + "\n\nPEER ANALYSIS:\n" + openai_view, evidence
    )
    openai_critique, openai_critique_error = openai(
        critique_prompt + "\n\nPEER ANALYSIS:\n" + anthropic_view, evidence
    )

    synthesis_prompt = (
        "You are the chair of a market-research discussion. Compare both independent analyses and their "
        "critiques. Produce a concise research consensus covering agreement, disagreement, evidence quality, "
        "uncertainty and data gaps. This is not a trading instruction. The trading engine, not an AI model, "
        "remains responsible for any strategy/risk/execution decision."
    )
    synthesis_evidence = {
        "market": evidence,
        "openai": openai_view,
        "anthropic": anthropic_view,
        "openai_critique": openai_critique,
        "anthropic_critique": anthropic_critique,
    }
    synthesis, synthesis_error = openai(synthesis_prompt, synthesis_evidence)

    write({
        "status": "COMPLETE" if synthesis else "SYNTHESIS_UNAVAILABLE",
        "timestamp": utc_now(),
        "paper_only": True,
        "independent": {"openai": openai_view, "anthropic": anthropic_view},
        "cross_review": {"openai": openai_critique, "anthropic": anthropic_critique},
        "consensus": synthesis or None,
        "errors": {
            "openai": openai_error,
            "anthropic": anthropic_error,
            "openai_cross_review": openai_critique_error,
            "anthropic_cross_review": anthropic_critique_error,
            "synthesis": synthesis_error,
        },
        "execution_authorized": False,
        "safety": {
            "live_orders_enabled": False,
            "ai_can_override_deterministic_gates": False,
            "stock_specific_rules_allowed": False,
        },
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
