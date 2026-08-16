#!/usr/bin/env python3
"""Build and validate the prospective development-only quality calibration packet."""
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "DEVELOPMENT_CALIBRATION_PACKET.json"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def unwrap_single_fence(value, language):
    lines = value.strip().splitlines()
    if len(lines) < 3 or lines[0] != f"```{language}" or lines[-1] != "```":
        return None
    body = "\n".join(lines[1:-1])
    if "```" in body:
        return None
    return body


def cases():
    categories = [
        "tool_call", "coding", "long_context_retrieval", "multi_turn_continuation",
        "teacher_forced_loss", "serving_correctness",
    ]
    rows = []
    for category in categories:
        for ordinal in range(1, 7):
            row = {
                "case_id": f"cal_dev_{category}_{ordinal:02d}",
                "category": category,
                "split": "development_calibration",
                "critical": True,
                "mutation_classes": ["wrong_value", "extra_prose", "wrong_schema"],
            }
            if category == "tool_call":
                row["contract"] = {"prompt_requirement": "Emit exactly one JSON object conforming to the supplied schema.", "schema": {"name": "read_file", "arguments": {"path": f"src/calibration_{ordinal}.py"}}}
            elif category == "coding":
                row["contract"] = {"accepted_transport": ["bare_python", "single_python_fence"], "rejected_transport": ["prose", "multiple_blocks", "wrong_fence"], "oracle": "executable_case_specific_tests"}
            elif category == "long_context_retrieval":
                row["contract"] = {"prompt_requirement": "Return only the value paired with the given key.", "wrong_value_control": f"calibration-wrong-{ordinal}"}
            elif category == "multi_turn_continuation":
                row["contract"] = {"prompt_requirement": "Return only the requested ordered parameter names.", "mutation_classes": ["wrong_order", "omission", "unrelated_turn"]}
            elif category == "teacher_forced_loss":
                row["contract"] = {"control_captures_required": 3, "ceiling_rule": "Freeze per-sequence ceiling to maximum BF16 control mean NLL times 1.05 after all development captures.", "runtime_evidence": "input_token_logprobs_and_token_sequence_hash"}
            else:
                row["contract"] = {"prompt_requirement": "Return exactly the supplied JSON schema without prose.", "repetitions": 2, "mutation_classes": ["missing_field", "wrong_type", "truncation"]}
            payload = canonical(row)
            rows.append({**row, "content_sha256": digest(payload)})
    return rows


def main():
    rows = cases()
    controls = {
        "single_fence_accept": unwrap_single_fence("```python\nx = 1\n```", "python") == "x = 1",
        "prose_reject": unwrap_single_fence("Answer:\n```python\nx = 1\n```", "python") is None,
        "wrong_fence_reject": unwrap_single_fence("```json\n{}\n```", "python") is None,
        "multiple_block_reject": unwrap_single_fence("```python\nx = 1\n```\n```python\ny = 2\n```", "python") is None,
        "schema_coercion_prohibited": {"arguments": {"file_path": "x"}} != {"arguments": {"path": "x"}},
        "wrong_value_reject": "calibration-wrong-1" != "calibration-value-1",
    }
    counts = Counter(row["category"] for row in rows)
    packet = {
        "schema_version": 1,
        "classification": "prospective_development_only_preregistration",
        "budget_usd": 0.0,
        "timeout_seconds": 300,
        "seed": 47021501,
        "scope": "Development calibration and local mutation controls only. No model call, new holdout generation, current-holdout access, serving change, or performance experiment is authorized.",
        "holdout_commitment_sha256": digest(b"glm47flash-quality-v2-holdout-seed-material-not-generated-until-development-seal"),
        "holdout_status": "not_generated_not_inspected",
        "cases": rows,
        "category_counts": dict(sorted(counts.items())),
        "controls": controls,
        "acceptance": {
            "local": "six categories with six fixtures each; fixture hashes validate; all transport/schema/value mutation controls pass",
            "future_control_capture": "Three intended BF16 captures must complete with raw runtime evidence and all category point scores at least 5/6 before freezing holdout contents and NLL ceilings",
            "future_candidate": "Only after holdout sealing: AWQ is eligible for paired evaluation with no critical regression over 1/6 and overall paired lower confidence bound at least -0.05"
        },
    }
    if counts != Counter({category: 6 for category in counts}) or len(counts) != 6 or not all(controls.values()):
        raise SystemExit("development calibration packet failed local acceptance")
    for row in rows:
        payload = dict(row)
        recorded = payload.pop("content_sha256")
        if digest(canonical(payload)) != recorded:
            raise SystemExit(f"fixture hash mismatch: {row['case_id']}")
    OUTPUT.write_bytes(json.dumps(packet, sort_keys=True, indent=2).encode() + b"\n")
    print(json.dumps({"packet_sha256": digest(OUTPUT.read_bytes()), "case_count": len(rows), "controls_pass": all(controls.values())}, sort_keys=True))


if __name__ == "__main__":
    main()
