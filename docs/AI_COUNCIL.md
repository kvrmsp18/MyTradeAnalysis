# AI Council: OpenAI + Anthropic

## Purpose

MyTradeAnalysis may use OpenAI and Anthropic as two independent AI research/advisory agents during paper trading. They receive the same decision-time evidence and are required to state their reasoning, uncertainty, risks and proposed action.

The agents may challenge each other, but **neither model is allowed to bypass deterministic trading gates**.

## Deliberation protocol

1. **Independent analysis** — OpenAI and Anthropic review the same market snapshot and candidate evidence without seeing the other's answer.
2. **Cross-critique** — Anthropic critiques the OpenAI proposal and OpenAI critiques the Anthropic proposal.
3. **Synthesis** — a final council response records the areas of agreement, disagreement, evidence quality and a proposed paper-trade action.
4. **Deterministic execution gate** — the trading engine checks market-data freshness, liquidity, capital, position limits, daily loss limits, risk/reward requirements, duplicate-order protection and all other hard safety rules.
5. **Paper execution only** — during the current phase, the final result can authorize only a simulated paper order. Live broker order submission remains disabled.

## Important separation

The AI council is an **advisory decision layer**, not the ultimate safety layer. A model cannot force an order when a deterministic gate says NO. Likewise, a model cannot create a stock-specific exception because a particular stock previously made money.

If the models disagree materially, the default is `HOLD_FOR_REVIEW` rather than forcing a trade.

## Required audit record

Each council decision should persist:

- timestamp
- candidate symbol
- exact decision-time evidence hash/reference
- OpenAI independent opinion
- Anthropic independent opinion
- OpenAI critique
- Anthropic critique
- synthesis
- disagreement fields
- confidence/uncertainty
- deterministic gate result
- final paper execution decision
- reason for rejection, if any

No provider API key is ever exposed to the browser GUI.

## Secrets

When the council is ready to run, configure GitHub Actions secrets:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Model names should be supplied through repository variables or environment configuration rather than hard-coded into trading logic.

The workflow must continue safely when either provider is unavailable: the missing provider is recorded as unavailable and no AI response is fabricated. If the required council quorum is not available, the AI layer cannot authorize a trade.
