#!/usr/bin/env python3
import json
import pathlib
import urllib.request


BASE = "http://127.0.0.1:30000"
CASES = [
    ("instruction", "Reply with exactly: READY"),
    ("arithmetic", "What is 2+2? Reply with only the number."),
    ("structured", 'Return only a JSON object with key "status" and string value "ok".'),
]


def main() -> int:
    output = pathlib.Path("/work/coherence.json")
    rows = []
    for label, prompt in CASES:
        body = {
            "model": "google/gemma-4-31B-it",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 32,
            "stream": False,
        }
        request = urllib.request.Request(
            BASE + "/v1/chat/completions",
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
        item = json.loads(raw)
        text = item["choices"][0]["message"]["content"]
        stripped = text.strip()
        if label == "instruction":
            passed = stripped == "READY"
        elif label == "arithmetic":
            passed = stripped == "4"
        else:
            try:
                passed = json.loads(stripped) == {"status": "ok"}
            except json.JSONDecodeError:
                passed = False
        rows.append(
            {
                "label": label,
                "prompt": prompt,
                "raw_response": raw.decode(errors="replace"),
                "text": text,
                "rule_pass": passed,
            }
        )
    result = {"schema_version": 1, "pass": all(x["rule_pass"] for x in rows), "rows": rows}
    temporary = output.with_name(output.name + ".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
