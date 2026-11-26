"""End-to-end quality check: GSM8K few-shot accuracy, stock vs candidate, same engine.

Usage on the GPU host: python3 -m tkcc.experiments.quality TIER [CANDIDATE.py] [N]
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

PORTS = {"fast": 18110, "slow": 18120}
DATA = Path("/home/tkcc/data/gsm8k_test.jsonl")


def _answer(text: str) -> str | None:
    match = re.search(r"####\s*(-?[\d,\.]+)", text)
    if match:
        return match.group(1).replace(",", "").rstrip(".")
    numbers = re.findall(r"-?\d[\d,]*\.?\d*", text)
    return numbers[-1].replace(",", "").rstrip(".") if numbers else None


def main() -> None:
    tier = sys.argv[1]
    candidate = Path(sys.argv[2]).read_text() if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 250
    rows = [json.loads(line) for line in DATA.read_text().splitlines()]
    shots, tests = rows[:4], rows[100 : 100 + count]
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file("/home/tkcc/models/dsv41/tokenizer.json")
    prefix = "".join(f"Question: {r['question']}\nAnswer: {r['answer']}\n\n" for r in shots)
    prompts = [tokenizer.encode(prefix + f"Question: {r['question']}\nAnswer:", add_special_tokens=False).ids for r in tests]
    body = json.dumps({"source": candidate, "prompts": prompts, "max_tokens": 320, "stop": ["\n\nQuestion:"]}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{PORTS[tier]}/generate", data=body, headers={"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(request, timeout=3600).read())
    if "error" in out:
        print(json.dumps(out))
        return
    correct = sum(_answer(text) == _answer(r["answer"]) for text, r in zip(out["texts"], tests))
    print(json.dumps({"tier": tier, "candidate": bool(candidate), "n": len(tests), "accuracy": correct / len(tests)}))


if __name__ == "__main__":
    main()
