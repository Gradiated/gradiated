from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DRAFT = ROOT / "DRAFT.md"
REQUIRED_ASSETS = {
    ROOT / "assets" / "endpoint-progress.svg",
    ROOT / "assets" / "hybrid-attention-map.svg",
    ROOT / "assets" / "ngram-verifier.svg",
}


def main() -> int:
    text = DRAFT.read_text(encoding="utf-8")
    words = re.findall(r"\b[\w'-]+\b", text)
    errors: list[str] = []

    if not 2700 <= len(words) <= 4500:
        errors.append(f"draft word count {len(words)} is outside 2700..4500")

    for asset in sorted(REQUIRED_ASSETS):
        if not asset.is_file():
            errors.append(f"missing asset: {asset.relative_to(ROOT)}")
            continue
        try:
            ET.parse(asset)
        except ET.ParseError as exc:
            errors.append(f"invalid SVG {asset.relative_to(ROOT)}: {exc}")

    for target in re.findall(r"!\[[^]]*\]\(([^)]+)\)", text):
        if "://" not in target and not (ROOT / target).is_file():
            errors.append(f"broken local image link: {target}")

    normalized_text = " ".join(text.split())
    required_phrases = (
        "Measured endpoint",
        "Source-complete, CPU-exact; target-GPU endpoint unmeasured",
        "not a claim of universal quality parity",
        "not an additive waterfall",
    )
    for phrase in required_phrases:
        if phrase not in normalized_text:
            errors.append(f"missing evidence guardrail: {phrase!r}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"verified: {len(words)} words, {len(REQUIRED_ASSETS)} SVGs, claim guardrails present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
