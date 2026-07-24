#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import urllib.request


BASE = "http://127.0.0.1:30000"
MODEL = "google/gemma-4-31B-it"


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent
    cases = [
        ("instruction", "Reply with exactly: READY"),
        ("arithmetic", "What is 2+2? Reply with only the number."),
        ("structured", 'Return only JSON with key "status" and value "ok".'),
    ]
    rows = []
    for label, prompt in cases:
        body = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "seed": 20260724,
            "max_tokens": 32,
            "stream": False,
            "return_token_ids": True,
        }
        request = urllib.request.Request(
            BASE + "/v1/chat/completions",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read()
        item = json.loads(raw)
        text = item["choices"][0]["message"]["content"]
        if label == "instruction":
            valid = "READY" in text.upper()
        elif label == "arithmetic":
            valid = text.strip().strip(".") == "4"
        else:
            try:
                valid = json.loads(text).get("status") == "ok"
            except (json.JSONDecodeError, AttributeError):
                valid = False
        rows.append(
            {
                "label": label,
                "text": text,
                "valid": valid,
                "raw": raw.decode(errors="replace"),
            }
        )
    terminal = {
        "schema_version": 1,
        "classification": "coherence_pass"
        if all(row["valid"] for row in rows)
        else "coherence_reject",
        "pass": all(row["valid"] for row in rows),
        "rows": rows,
    }
    atomic(root / "COHERENCE_TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 72


if __name__ == "__main__":
    raise SystemExit(main())
