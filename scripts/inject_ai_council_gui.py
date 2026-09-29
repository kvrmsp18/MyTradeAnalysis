"""Validate AI-council GUI wiring without mutating the React source.

The GUI now owns its OpenAI/Anthropic council integration. This deployment
step is intentionally idempotent: it validates the required wiring and
fails loudly if the source regresses, rather than injecting duplicate
constants or components into src/App.jsx.
"""
from pathlib import Path

APP = Path("src/App.jsx")

REQUIRED = [
    "const COUNCIL='/MyTradeAnalysis/data/ai_research_council.json';",
    "const [council,setCouncil]=useState(null);",
    "fetch(COUNCIL+'?t='+Date.now())",
    "setCouncil(nextCouncil);",
    "council={council}",
    "OpenAI",
    "Anthropic",
]


def main() -> int:
    if not APP.exists():
        raise SystemExit("AI council GUI validation failed: src/App.jsx is missing.")

    source = APP.read_text(encoding="utf-8")
    missing = [needle for needle in REQUIRED if needle not in source]
    if missing:
        raise SystemExit(
            "AI council GUI validation failed; required wiring is missing: "
            + ", ".join(missing)
        )

    # Catch the exact class of regression shown by the failed Pages build:
    # duplicate top-level COUNCIL declarations.
    declaration = "const COUNCIL='/MyTradeAnalysis/data/ai_research_council.json';"
    count = source.count(declaration)
    if count != 1:
        raise SystemExit(
            f"AI council GUI validation failed: expected exactly 1 COUNCIL "
            f"declaration, found {count}."
        )

    print("AI council GUI wiring: PASS")
    print("OpenAI + Anthropic data path: present")
    print("Duplicate COUNCIL declaration check: PASS")
    print("Deployment script made no source mutation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
