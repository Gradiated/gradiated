#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, pathlib, random
from tool_bridge_worker import normalize_response, sha_bytes

PROJECT = pathlib.Path(__file__).parent
RUN = PROJECT / "artifacts/tool-bridge-20260720t0458z"
REMOTE = RUN / "remote-tool-bridge"
RAW = PROJECT / "artifacts/v0513-fp8-quality-recovery-repair-20260720t0425z/remote-quality/captures"
BINDING = json.loads((PROJECT / "tool_bridge_bindings.json").read_text())

def atomic(path: pathlib.Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    tmp.replace(path)

def validate_sentinel(check: dict) -> dict:
    observed = [[name, args] for name, args in check["observed"]]
    expected = [[name, args] for name, args in check["expected"]]
    usage = check.get("usage") or {}
    usage_ok = all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
    return {**check, "pass": observed == expected and check.get("finish_reason") == "tool_calls" and usage_ok}

def main() -> int:
    terminal = json.loads((REMOTE / "SENTINEL_TERMINAL.json").read_text())
    arms = {}
    for arm, data in terminal["arms"].items():
        arms[arm] = {**data, "sentinels": [{**row, "check": validate_sentinel(row["check"])} for row in data["sentinels"]]}
    gate = terminal["parser_byte_identical"] and all(row["check"]["pass"] for data in arms.values() for row in data["sentinels"])
    rescore = {}
    requests = {row["case_id"]: row for row in (json.loads(x) for x in (PROJECT / "assets/requests/taubench_requests.jsonl").read_text().splitlines())}
    outdir = RUN / "rescore"; outdir.mkdir(exist_ok=True)
    for arm in ("bf16", "fp8"):
        source = RAW / f"{arm}-tau.jsonl"; source_hash = sha_bytes(source.read_bytes())
        if source_hash != BINDING[f"{arm}_tau_raw_sha256"]: raise RuntimeError(f"raw_hash_mismatch_{arm}")
        rows = []; passed = 0
        for line in source.read_text().splitlines():
            row = json.loads(line); normalized = normalize_response(row["raw_response"]); calls = []
            for call in (((normalized.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []):
                fn = call.get("function") or {}
                calls.append({"name": fn.get("name"), "arguments": json.loads(fn.get("arguments", "{}"))})
            expected = requests[row["case_id"]].get("expected_actions", []); expected_names = [x["name"] for x in expected]; observed_names = [x["name"] for x in calls]; ok = observed_names[:len(expected_names)] == expected_names; passed += int(ok)
            rows.append({"case_id": row["case_id"], "source_raw_response_sha256": row["raw_response_bytes_sha256"], "observed_actions": calls, "observed_action_names": observed_names, "expected_actions": expected, "scorer": "prefix_action_names_v0513", "pass": ok, "parser_sha256": terminal["parser_sha256"]})
        out = outdir / f"{arm}.jsonl"; out.write_text("\n".join(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in rows) + "\n")
        rescore[arm] = {"count": len(rows), "task_success": passed / len(rows), "source_sha256": source_hash, "normalized_sha256": sha_bytes(out.read_bytes()), "parser_sha256": terminal["parser_sha256"]}
    bf = {x["case_id"]: x["pass"] for x in (json.loads(line) for line in (outdir / "bf16.jsonl").read_text().splitlines())}; fp = {x["case_id"]: x["pass"] for x in (json.loads(line) for line in (outdir / "fp8.jsonl").read_text().splitlines())}; delta = [int(fp[k]) - int(bf[k]) for k in bf]; rng = random.Random(20260720); boot = sorted(sum(delta[rng.randrange(len(delta))] for _ in delta) / len(delta) for _ in range(10000))
    final = {"schema_version": 1, "classification": "tool_consumer_gate_complete", "pass": gate, "parser_mode": terminal["parser_mode"], "parser_sha256": terminal["parser_sha256"], "checkpoint_schema_sha256": terminal["checkpoint_schema_sha256"], "image": terminal["image"], "image_probe": terminal["image_probe"], "parser_byte_identical": terminal["parser_byte_identical"], "arms": arms, "rescore": rescore, "paired_bootstrap": {"seed": 20260720, "replicates": 10000, "candidate_minus_control_mean": sum(delta) / len(delta), "ci_95": [boot[250], boot[9750]]}, "request_counts": {"bf16_tau": rescore["bf16"]["count"], "fp8_tau": rescore["fp8"]["count"]}, "source_terminal": str(REMOTE / "SENTINEL_TERMINAL.json"), "source_terminal_sha256": sha_bytes((REMOTE / "SENTINEL_TERMINAL.json").read_bytes())}
    old = json.loads((RUN / "TERMINAL.json").read_text()); final["provider_exposure_seconds"] = old.get("provider_exposure_seconds"); final["provider_spend_usd"] = old.get("provider_spend_usd"); final["project_cumulative_spend_usd"] = 1.753897390753883 + sum(json.loads((PROJECT / f"artifacts/tool-bridge-20260720t0{stamp}z/TERMINAL.json").read_text()).get("provider_spend_usd", 0.0) for stamp in ("448", "452", "458"))
    atomic(RUN / "FINAL_TERMINAL.json", final)
    return 0 if gate else 1

if __name__ == "__main__": raise SystemExit(main())
