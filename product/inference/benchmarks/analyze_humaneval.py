#!/usr/bin/env python3
"""Execute BF16 and candidate HumanEval generations under an outer sandbox."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


EOS_IDS = frozenset({1, 106})
FENCED_CODE = re.compile(r"```(?:python|py)?\s*\n(.*?)(?:```|\Z)", re.DOTALL)


def through_eos(tokens: list[int]) -> list[int]:
    for index, token in enumerate(tokens):
        if token in EOS_IDS:
            return tokens[: index + 1]
    return tokens


def source(text: str, prompt: str, entry_point: str) -> str:
    fenced = FENCED_CODE.search(text)
    if fenced:
        text = fenced.group(1)
    text = text.strip()
    definition = re.search(rf"(?m)^(?:async\s+)?def\s+{re.escape(entry_point)}\s*\(", text)
    if definition:
        imports = "\n".join(
            line for line in text[: definition.start()].splitlines()
            if line.startswith("import ") or line.startswith("from ")
        )
        return (imports + "\n" if imports else "") + text[definition.start() :]
    # Canonical HumanEval completions continue the supplied function body.
    continuation = "\n".join(
        line if not line.strip() or line.startswith((" ", "\t")) else "    " + line
        for line in text.splitlines()
    )
    return prompt + continuation


def execute(program: str, test: str, entry_point: str, timeout: float) -> tuple[bool, str]:
    payload = program + "\n\n" + test + f"\n\ncheck({entry_point})\n"
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", payload],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env={"PYTHONHASHSEED": "0"},
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    if result.returncode == 0:
        return True, ""
    error = result.stderr.strip().splitlines()
    return False, error[-1][:300] if error else f"exit {result.returncode}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--maximum-regressions", type=int, default=0)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    prompts = {item["id"]: item for item in fixture["prompts"]}
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    records = [
        json.loads(line)
        for line in args.generations.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for record in records:
        key = (
            record["scaling"],
            record.get("weight_scale_multiplier", 1.0),
            record.get("weight_mse_calibration", False),
            record["bf16_layers"],
        )
        cases.setdefault(key, []).append(record)

    reports: list[dict[str, object]] = []
    all_passed = True
    for key, case_records in sorted(cases.items(), key=lambda item: str(item[0])):
        identifiers = [str(record["id"]) for record in case_records]
        duplicates = sorted(
            identifier for identifier in set(identifiers)
            if identifiers.count(identifier) > 1
        )
        if duplicates:
            raise RuntimeError(
                f"generation case has duplicate task ids: {', '.join(duplicates)}"
            )
        unknown = sorted(set(identifiers) - set(prompts))
        missing = sorted(set(prompts) - set(identifiers))
        if unknown or missing:
            raise RuntimeError(
                "generation case does not match fixture: "
                f"unknown={unknown}, missing={missing}"
            )
        details: list[dict[str, object]] = []
        for record in case_records:
            identifier = str(record["id"])
            task = prompts[identifier]
            reference_text = tokenizer.decode(
                through_eos([int(token) for token in record["reference_ids"]]),
                skip_special_tokens=True,
            )
            candidate_text = tokenizer.decode(
                through_eos([int(token) for token in record["candidate_ids"]]),
                skip_special_tokens=True,
            )
            reference_passed, reference_error = execute(
                source(reference_text, str(task["prompt"]), str(task["entry_point"])),
                str(task["test"]),
                str(task["entry_point"]),
                args.timeout,
            )
            candidate_passed, candidate_error = execute(
                source(candidate_text, str(task["prompt"]), str(task["entry_point"])),
                str(task["test"]),
                str(task["entry_point"]),
                args.timeout,
            )
            details.append(
                {
                    "id": identifier,
                    "reference_passed": reference_passed,
                    "candidate_passed": candidate_passed,
                    "regression": reference_passed and not candidate_passed,
                    "improvement": candidate_passed and not reference_passed,
                    "reference_error": reference_error,
                    "candidate_error": candidate_error,
                }
            )
        reference_passes = sum(item["reference_passed"] for item in details)
        candidate_passes = sum(item["candidate_passed"] for item in details)
        regressions = sum(item["regression"] for item in details)
        improvements = sum(item["improvement"] for item in details)
        passed = regressions <= args.maximum_regressions and candidate_passes >= reference_passes
        all_passed &= passed
        reports.append(
            {
                "scaling": key[0],
                "weight_scale_multiplier": key[1],
                "weight_mse_calibration": key[2],
                "bf16_layers": key[3],
                "tasks": len(details),
                "reference_passes": reference_passes,
                "candidate_passes": candidate_passes,
                "reference_pass_at_1": reference_passes / len(details),
                "candidate_pass_at_1": candidate_passes / len(details),
                "regressions": regressions,
                "improvements": improvements,
                "passed": passed,
                "details": details,
            }
        )

    payload = {
        "schema": "gradiated.humaneval-report.v1",
        "passed": all_passed,
        "maximum_regressions": args.maximum_regressions,
        "cases": reports,
    }
    if args.output:
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": all_passed,
                "cases": [
                    {name: value for name, value in report.items() if name != "details"}
                    for report in reports
                ],
            },
            indent=2,
        )
    )
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
