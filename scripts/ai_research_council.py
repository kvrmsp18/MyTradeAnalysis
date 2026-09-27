#!/usr/bin/env python3
"""Run a non-executing OpenAI + Anthropic research council.

Both models receive the same decision-time market snapshot and deterministic
SCRAP technical evidence. They work independently, cross-critique each other,
and produce a research synthesis. The council is advisory only: deterministic
capital, market-data, liquidity, risk and duplicate-order gates remain the
only authority over execution.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT = Path("public/data/market_snapshot.json")
SCRAP = Path("public/data/scrap_analysis.json")
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
            {
                "model": model,
                "input": prompt + "\n\nEVIDENCE:\n" + json.dumps(evidence, sort_keys=True),
                "store": False,
            },
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
            {
                "model": model,
                "max_tokens": 1200,
                "messages": [{"role": "user", "content": prompt + "\n\nEVIDENCE:\n" + json.dumps(evidence, sort_keys=True)}],
            },
        )
        text = anthropic_text(data)
        return (text, None) if text else ("", "Anthropic returned no text.")
    except Exception as exc:
        return "", f"Anthropic unavailable: {exc}"


def write(data: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else fallback
    except (OSError, json.JSONDecodeError):
        return fallback


def main() -> int:
    if not SNAPSHOT.exists():
        write({"status": "UNAVAILABLE", "timestamp": utc_now(), "reason": "Market snapshot missing."})
        return 0

    market = load(SNAPSHOT, {"status": "DATA_UNAVAILABLE", "stocks": []})
    scrap = load(SCRAP, {"status": "NOT_RUN", "stocks": []})
    if market.get("status") != "LIVE_MARKET_DATA":
        write({"status": "UNAVAILABLE", "timestamp": utc_now(), "reason": "No verified market data available."})
        return 0

    evidence = {"market_snapshot": market, "scrap_analysis": scrap}
    analyst_prompt = (
        "You are an independent market-research analyst inside a paper-trading research system. "
        "Review only the supplied decision-time market snapshot and deterministic SCRAP evidence. "
        "Do not invent prices, news, indicators or fundamentals. Assess the technical evidence, "
        "market context, contradictions, uncertainty, missing data and risk blind spots. "
        "You may state an advisory view such as SUPPORTS_REVIEW, WATCH_ONLY or NO_SUPPORT, but "
        "never issue an executable order or override a deterministic gate. End with questions "
        "another analyst should challenge."
    )
    openai_view, openai_error = openai(analyst_prompt, evidence)
    anthropic_view, anthropic_error = anthropic(analyst_prompt, evidence)

    if not openai_view or not anthropic_view:
        write({
            "status": "QUORUM_UNAVAILABLE",
            "timestamp": utc_now(),
            "paper_only": True,
            "independent": {"openai": openai_view or None, "anthropic": anthropic_view or None},
            "cross_review": {"openai": None, "anthropic": None},
            "consensus": None,
            "errors": {"openai": openai_error, "anthropic": anthropic_error},
            "execution_authorized": False,
        })
        return 0

    critique_prompt = (
        "You are the second-pass reviewer in a two-model research council. Review the peer analysis "
        "against the same market and SCRAP evidence. Identify unsupported claims, missing evidence, "
        "contradictions and risk blind spots. Give a short challenge and state whether the peer's "
        "research view is supported by the supplied evidence. Do not issue an executable trade order."
    )
    anthropic_critique, anthropic_critique_error = anthropic(
        critique_prompt + "\n\nPEER ANALYSIS:\n" + openai_view, evidence
    )
    openai_critique, openai_critique_error = openai(
        critique_prompt + "\n\nPEER ANALYSIS:\n" + anthropic_view, evidence
    )

    synthesis_prompt = (
        "You are the chair of a market-research discussion. Compare both independent analyses and "
        "their cross-critiques against the same deterministic evidence. Produce a concise research "
        "consensus covering agreement, disagreement, technical evidence quality, uncertainty and "
        "data gaps. If the evidence is insufficient, say so explicitly. The council may classify "
        "research support as SUPPORTS_REVIEW, WATCH_ONLY or NO_SUPPORT, but this classification is "
        "advisory only. Never authorize or submit an order. The deterministic trading engine remains "
        "responsible for all strategy, capital, risk and execution decisions."
    )
    synthesis_evidence = {
        "market": market,
        "scrap": scrap,
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
