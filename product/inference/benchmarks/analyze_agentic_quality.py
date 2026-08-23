#!/usr/bin/env python3
"""Gate native precision candidates on held-out agent-completion behavior.

The BF16 run is the numerical reference. The recorded trace response is used
only to identify the expected response shape (for example, a shell action),
because it may have been produced by a different model.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import math
import re
import statistics
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

EOS_IDS = frozenset({1, 106})
FENCE = re.compile(r"```[ \t]*([\w+.-]*)[^\n]*\n(.*?)(?:```|\Z)", re.DOTALL)
THOUGHT = re.compile(r"(?im)^\s*(?:thought|analysis)\s*:")
SHELL_LANGUAGES = frozenset({"bash", "sh", "shell", "zsh", "console"})
PYTHON_LANGUAGES = frozenset({"python", "py"})
JSON_LANGUAGES = frozenset({"json", "jsonc"})


@dataclass(frozen=True)
class Shape:
    has_thought: bool
    has_fence: bool
    has_shell: bool
    has_python: bool
    has_json: bool
    balanced_fences: bool
    syntax_valid: bool
    replacement_characters: int


def token_edit_similarity(left: list[int], right: list[int]) -> float:
    return difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()


def through_eos(tokens: list[int]) -> list[int]:
    for index, token in enumerate(tokens):
        if token in EOS_IDS:
            return tokens[: index + 1]
    return tokens


def shell_valid(source: str) -> bool:
    # --noexec parses without running commands, expansions, or substitutions.
    result = subprocess.run(
        ["bash", "-n"],
        input=source,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def classify(text: str) -> Shape:
    blocks = [(language.lower(), body) for language, body in FENCE.findall(text)]
    syntax_results: list[bool] = []
    for language, body in blocks:
        if language in SHELL_LANGUAGES:
            syntax_results.append(shell_valid(body))
        elif language in PYTHON_LANGUAGES:
            try:
                ast.parse(body)
                syntax_results.append(True)
            except SyntaxError:
                syntax_results.append(False)
        elif language in JSON_LANGUAGES:
            try:
                json.loads(body)
                syntax_results.append(True)
            except json.JSONDecodeError:
                syntax_results.append(False)
    return Shape(
        has_thought=bool(THOUGHT.search(text)),
        has_fence="```" in text,
        has_shell=any(language in SHELL_LANGUAGES for language, _ in blocks),
        has_python=any(language in PYTHON_LANGUAGES for language, _ in blocks),
        has_json=any(language in JSON_LANGUAGES for language, _ in blocks),
        balanced_fences=text.count("```") % 2 == 0,
        syntax_valid=all(syntax_results),
        replacement_characters=text.count("\ufffd"),
    )


def source_requirements(shape: Shape) -> tuple[str, ...]:
    return tuple(
        name
        for name in ("has_thought", "has_fence", "has_shell", "has_python", "has_json")
        if getattr(shape, name)
    )


def structural_regressions(source: Shape, reference: Shape, candidate: Shape) -> list[str]:
    regressions: list[str] = []
    for field in source_requirements(source):
        if getattr(reference, field) and not getattr(candidate, field):
            regressions.append(field)
    if reference.balanced_fences and not candidate.balanced_fences:
        regressions.append("balanced_fences")
    if reference.syntax_valid and not candidate.syntax_valid:
        regressions.append("syntax_valid")
    if candidate.replacement_characters > reference.replacement_characters:
        regressions.append("replacement_characters")
    return regressions


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--maximum-tokens",
        type=int,
        default=0,
        help="truncate stored generations before EOS analysis (zero keeps all tokens)",
    )
    parser.add_argument("--minimum-mean-edit-similarity", type=float, default=0.95)
    parser.add_argument("--minimum-p05-edit-similarity", type=float, default=0.60)
    parser.add_argument("--maximum-eos-regressions", type=int, default=0)
    parser.add_argument("--maximum-structural-regressions", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from transformers import AutoTokenizer

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    prompts = {item["id"]: item for item in fixture["prompts"]}
    records = [
        json.loads(line)
        for line in args.generations.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        raise RuntimeError("generation artifact is empty")
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)

    cases: dict[tuple[str, float, bool, str], list[dict[str, object]]] = {}
    for record in records:
        key = (
            str(record["scaling"]),
            float(record.get("weight_scale_multiplier", 1.0)),
            bool(record.get("weight_mse_calibration", False)),
            str(record["bf16_layers"]),
        )
        cases.setdefault(key, []).append(record)

    reports: list[dict[str, object]] = []
    all_passed = True
    for (scaling, weight_scale_multiplier, weight_mse_calibration, bf16_layers), case_records in sorted(
        cases.items()
    ):
        details: list[dict[str, object]] = []
        similarities: list[float] = []
        eos_regressions = 0
        structural_regression_events = 0
        structural_regression_prompts = 0
        for record in case_records:
            identifier = str(record["id"])
            if identifier not in prompts:
                raise RuntimeError(f"generation has unknown prompt id {identifier}")
            reference_ids = [int(token) for token in record["reference_ids"]]
            candidate_ids = [int(token) for token in record["candidate_ids"]]
            if args.maximum_tokens:
                if args.maximum_tokens < 0:
                    raise ValueError("--maximum-tokens must be non-negative")
                reference_ids = reference_ids[: args.maximum_tokens]
                candidate_ids = candidate_ids[: args.maximum_tokens]
            reference_ids = through_eos(reference_ids)
            candidate_ids = through_eos(candidate_ids)
            reference_text = tokenizer.decode(reference_ids, skip_special_tokens=True)
            candidate_text = tokenizer.decode(candidate_ids, skip_special_tokens=True)
            source_text = str(prompts[identifier].get("source_response", ""))
            source_shape = classify(source_text)
            reference_shape = classify(reference_text)
            candidate_shape = classify(candidate_text)
            regressions = structural_regressions(
                source_shape, reference_shape, candidate_shape
            )
            reference_eos = bool(reference_ids and reference_ids[-1] in EOS_IDS)
            candidate_eos = bool(candidate_ids and candidate_ids[-1] in EOS_IDS)
            eos_regression = reference_eos and not candidate_eos
            similarity = token_edit_similarity(reference_ids, candidate_ids)
            similarities.append(similarity)
            eos_regressions += int(eos_regression)
            structural_regression_events += len(regressions)
            structural_regression_prompts += int(bool(regressions))
            details.append(
                {
                    "id": identifier,
                    "token_edit_similarity": round(similarity, 6),
                    "reference_tokens": len(reference_ids),
                    "candidate_tokens": len(candidate_ids),
                    "reference_eos": reference_eos,
                    "candidate_eos": candidate_eos,
                    "eos_regression": eos_regression,
                    "source_requirements": source_requirements(source_shape),
                    "reference_shape": asdict(reference_shape),
                    "candidate_shape": asdict(candidate_shape),
                    "structural_regressions": regressions,
                }
            )
        missing = sorted(set(prompts) - {str(record["id"]) for record in case_records})
        if missing:
            raise RuntimeError(f"generation case is missing {len(missing)} fixture prompts")
        mean_similarity = statistics.fmean(similarities)
        p05_similarity = percentile(similarities, 0.05)
        gates = {
            "mean_edit_similarity": mean_similarity
            >= args.minimum_mean_edit_similarity,
            "p05_edit_similarity": p05_similarity
            >= args.minimum_p05_edit_similarity,
            "eos_regressions": eos_regressions <= args.maximum_eos_regressions,
            "structural_regressions": structural_regression_prompts
            <= args.maximum_structural_regressions,
        }
        passed = all(gates.values())
        all_passed &= passed
        reports.append(
            {
                "scaling": scaling,
                "weight_scale_multiplier": weight_scale_multiplier,
                "weight_mse_calibration": weight_mse_calibration,
                "bf16_layers": bf16_layers,
                "prompts": len(case_records),
                "mean_token_edit_similarity": round(mean_similarity, 6),
                "p05_token_edit_similarity": round(p05_similarity, 6),
                "exact_sequences": sum(
                    detail["token_edit_similarity"] == 1.0 for detail in details
                ),
                "reference_eos": sum(detail["reference_eos"] for detail in details),
                "candidate_eos": sum(detail["candidate_eos"] for detail in details),
                "eos_regressions": eos_regressions,
                "structural_regression_prompts": structural_regression_prompts,
                "structural_regression_events": structural_regression_events,
                "gates": gates,
                "passed": passed,
                "details": details,
            }
        )

    payload = {
        "schema": "gradiated.agentic-quality-report.v1",
        "fixture": str(args.fixture),
        "generations": str(args.generations),
        "thresholds": {
            "minimum_mean_edit_similarity": args.minimum_mean_edit_similarity,
            "minimum_p05_edit_similarity": args.minimum_p05_edit_similarity,
            "maximum_eos_regressions": args.maximum_eos_regressions,
            "maximum_structural_regressions": args.maximum_structural_regressions,
        },
        "passed": all_passed,
        "cases": reports,
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": all_passed,
                "cases": [
                    {key: value for key, value in report.items() if key != "details"}
                    for report in reports
                ],
            },
            indent=2,
        )
    )
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
