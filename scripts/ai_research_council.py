#!/usr/bin/env python3
"""Run a non-executing OpenAI + Anthropic research council.

Both models receive the same decision-time market snapshot and deterministic
SCRAP technical evidence. They work independently, cross-critique the peer,
and then independently produce a final council position. A deterministic
consensus rule records agreement or disagreement. The council is advisory
only: deterministic capital, market-data, liquidity, risk and duplicate-order
gates remain the only authority over execution.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT = Path("public/data/market_snapshot.json")
SCRAP = Path("public/data/scrap_analysis.json")
OUT = Path("public/data/ai_research_council.json")

ALLOWED_CLASSIFICATIONS = {"SUPPORTS_REVIEW", "WATCH_ONLY", "NO_SUPPORT"}


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
        item.get("text", "")
        for item in data.get("content", [])
        if isinstance(item, dict) and item.get("type") == "text"
    ).strip()


def extract_classification(text: str) -> str | None:
    """Read only an explicit model classification; never infer one."""
    match = re.search(
        r"(?:^|\n)\s*CLASSIFICATION\s*:\s*(SUPPORTS_REVIEW|WATCH_ONLY|NO_SUPPORT)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1).upper()
    return value if value in ALLOWED_CLASSIFICATIONS else None


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
                "max_tokens": 1400,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                        + "\n\nEVIDENCE:\n"
                        + json.dumps(evidence, sort_keys=True),
                    }
                ],
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


def unavailable(reason: str, market: dict | None = None, scrap: dict | None = None) -> int:
    write(
        {
            "status": "UNAVAILABLE",
            "timestamp": utc_now(),
            "paper_only": True,
            "reason": reason,
            "market_status": (market or {}).get("status"),
            "scrap_status": (scrap or {}).get("status"),
            "execution_authorized": False,
        }
    )
    return 0


def main() -> int:
    if not SNAPSHOT.exists():
        return unavailable("Market snapshot missing.")

    market = load(SNAPSHOT, {"status": "DATA_UNAVAILABLE", "stocks": []})
    scrap = load(SCRAP, {"status": "NOT_RUN", "stocks": []})
    if market.get("status") != "LIVE_MARKET_DATA":
        return unavailable("No verified market data available.", market, scrap)

    evidence = {"market_snapshot": market, "scrap_analysis": scrap}

    independent_prompt = (
        "You are an independent market-research analyst inside a paper-trading research system. "
        "Review only the supplied decision-time market snapshot and deterministic SCRAP evidence. "
        "Do not invent prices, news, indicators or fundamentals. Assess technical evidence, market "
        "context, contradictions, uncertainty, missing data and risk blind spots. You may classify "
        "the research evidence as SUPPORTS_REVIEW, WATCH_ONLY or NO_SUPPORT. This is an advisory "
        "research classification, not an order. Start your response with exactly one line in the "
        "form CLASSIFICATION: <value>. End with questions another analyst should challenge."
    )

    openai_view, openai_error = openai(independent_prompt, evidence)
    anthropic_view, anthropic_error = anthropic(independent_prompt, evidence)

    if not openai_view or not anthropic_view:
        write(
            {
                "status": "QUORUM_UNAVAILABLE",
                "timestamp": utc_now(),
                "paper_only": True,
                "independent": {
                    "openai": openai_view or None,
                    "anthropic": anthropic_view or None,
                },
                "classifications": {
                    "openai": extract_classification(openai_view),
                    "anthropic": extract_classification(anthropic_view),
                },
                "cross_review": {"openai": None, "anthropic": None},
                "final_positions": {"openai": None, "anthropic": None},
                "consensus": {
                    "status": "QUORUM_UNAVAILABLE",
                    "classification": "HOLD_FOR_REVIEW",
                },
                "errors": {"openai": openai_error, "anthropic": anthropic_error},
                "execution_authorized": False,
            }
        )
        return 0

    critique_prompt = (
        "You are a peer reviewer in a two-model market-research council. Review the peer analysis "
        "against the same supplied market and SCRAP evidence. Identify unsupported claims, missing "
        "evidence, contradictions and risk blind spots. State whether the peer's research position "
        "is supported by the evidence. Do not issue an executable trade order."
    )

    anthropic_critique, anthropic_critique_error = anthropic(
        critique_prompt + "\n\nPEER ANALYSIS (OpenAI):\n" + openai_view,
        evidence,
    )
    openai_critique, openai_critique_error = openai(
        critique_prompt + "\n\nPEER ANALYSIS (Anthropic):\n" + anthropic_view,
        evidence,
    )

    final_prompt = (
        "You are completing the final pass of a two-model research council. Review your original "
        "analysis, the peer's analysis, both cross-critiques, and the same deterministic market/SCRAP "
        "evidence. Reassess your research classification. Do not follow the peer merely because it "
        "is confident. Explicitly identify agreement, disagreement, uncertainty and data gaps. "
        "This remains advisory research and must never authorize, submit, or override an order. "
        "Start with exactly one line: CLASSIFICATION: SUPPORTS_REVIEW, CLASSIFICATION: WATCH_ONLY, "
        "or CLASSIFICATION: NO_SUPPORT."
    )

    openai_final, openai_final_error = openai(
        final_prompt
        + "\n\nYOUR ORIGINAL ANALYSIS:\n"
        + openai_view
        + "\n\nPEER (Anthropic):\n"
        + anthropic_view
        + "\n\nYOUR CRITIQUE OF PEER:\n"
        + openai_critique
        + "\n\nPEER CRITIQUE OF YOU:\n"
        + anthropic_critique,
        evidence,
    )
    anthropic_final, anthropic_final_error = anthropic(
        final_prompt
        + "\n\nYOUR ORIGINAL ANALYSIS:\n"
        + anthropic_view
        + "\n\nPEER (OpenAI):\n"
        + openai_view
        + "\n\nYOUR CRITIQUE OF PEER:\n"
        + anthropic_critique
        + "\n\nPEER CRITIQUE OF YOU:\n"
        + openai_critique,
        evidence,
    )

    openai_class = extract_classification(openai_final)
    anthropic_class = extract_classification(anthropic_final)

    if not openai_final or not anthropic_final:
        consensus_status = "QUORUM_UNAVAILABLE"
        consensus_class = "HOLD_FOR_REVIEW"
    elif not openai_class or not anthropic_class:
        consensus_status = "CLASSIFICATION_UNAVAILABLE"
        consensus_class = "HOLD_FOR_REVIEW"
    elif openai_class == anthropic_class:
        consensus_status = "AGREEMENT"
        consensus_class = openai_class
    else:
        consensus_status = "DISAGREEMENT"
        consensus_class = "HOLD_FOR_REVIEW"

    write(
        {
            "status": "COMPLETE" if openai_final and anthropic_final else "SYNTHESIS_UNAVAILABLE",
            "timestamp": utc_now(),
            "paper_only": True,
            "independent": {"openai": openai_view, "anthropic": anthropic_view},
            "independent_classifications": {
                "openai": extract_classification(openai_view),
                "anthropic": extract_classification(anthropic_view),
            },
            "cross_review": {
                "openai": openai_critique,
                "anthropic": anthropic_critique,
            },
            "final_positions": {
                "openai": openai_final or None,
                "anthropic": anthropic_final or None,
            },
            "final_classifications": {
                "openai": openai_class,
                "anthropic": anthropic_class,
            },
            "consensus": {
                "status": consensus_status,
                "classification": consensus_class,
                "rule": "Only exact agreement between both final classifications produces a research classification; otherwise HOLD_FOR_REVIEW.",
            },
            "errors": {
                "openai": openai_error,
                "anthropic": anthropic_error,
                "openai_cross_review": openai_critique_error,
                "anthropic_cross_review": anthropic_critique_error,
                "openai_final": openai_final_error,
                "anthropic_final": anthropic_final_error,
            },
            "execution_authorized": False,
            "safety": {
                "live_orders_enabled": False,
                "ai_can_override_deterministic_gates": False,
                "stock_specific_rules_allowed": False,
                "disagreement_defaults_to_hold": True,
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
