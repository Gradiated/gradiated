#!/usr/bin/env python3
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT.parent
RUNTIME = PROJECTS / "gemma4_upstream_ngram_runtime_rebase"
ENDPOINT = (
    RUNTIME
    / "artifacts/v0515-endpoint-20260725t062540z/retrieved-final/"
    "endpoint-stage/out-endpoint"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def function_source(path: Path, name: str) -> str:
    source = path.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node)
    raise AssertionError(f"missing function {name} in {path}")


def verify_binding() -> dict:
    binding = json.loads((ROOT / "DIRECTOR_BINDING.json").read_text())
    checked = {}
    for group in (binding["full_endpoint"], binding["passing_discriminator"]):
        for prefix in ("requests", "terminal"):
            path = ROOT / group[f"{prefix}_path"]
            expected = group[f"{prefix}_sha256"]
            actual = digest(path)
            assert actual == expected, (path, actual, expected)
            checked[str(path.resolve())] = actual
    for group in binding["source_identities"].values():
        path = ROOT / group["path"]
        actual = digest(path)
        assert actual == group["sha256"], (path, actual, group["sha256"])
        checked[str(path.resolve())] = actual
    return checked


def main() -> None:
    checked = verify_binding()
    rows = load_jsonl(ROOT / "inputs/v0515_endpoint_requests.jsonl")
    controls = load_jsonl(ROOT / "inputs/exact_semantic_rows.jsonl")
    assert len(rows) == 791
    assert [row["i"] for row in rows] == list(range(791))
    mismatches = [
        {
            "request": row["i"],
            "output_token_index": row["first_output_token_mismatch"],
        }
        for row in rows
        if not row["semantic_matches_bound"]
    ]
    assert mismatches == [
        {"request": 217, "output_token_index": 19},
        {"request": 512, "output_token_index": 37},
    ]
    assert all(
        token == 51935
        for row in rows[:217]
        for token in row["semantic"]["output_ids"]
    )
    request_217 = rows[217]["semantic"]["output_ids"]
    assert request_217[:19] == [51935] * 19
    assert request_217[19:] == [3055] * 339
    assert controls[217]["semantic"]["output_ids"] == [51935] * 358

    trace = json.loads((ROOT / "inputs/TRACE_PACKET.json").read_text())
    template = next(
        group for group in trace["primary_groups"] if group["name"] == "primary_c1"
    )["scored"][0]["request_body"]
    prompt_tail = template["prompt"][-18:]
    assert prompt_tail[-1] == 51935
    assert 3055 not in prompt_tail

    worker = ROOT / "source/ngram_worker.py"
    prepare = function_source(worker, "_prepare_draft_tokens")
    update = function_source(worker, "_update_ngram_corpus")
    forward = function_source(worker, "forward_batch_generation")
    assert "req.output_ids[-self.max_trie_depth :]" in prepare
    assert "req.output_ids[-self.max_trie_depth :]" in update
    assert "eagle_sample(verify_input, batch, logits_output, vocab_mask)" in forward
    assert "accept_tokens = predict[accept_index].flatten()" in forward
    assert "num_correct_drafts_per_req = accept_lens - 1" in forward

    sample = function_source(ROOT / "source/eagle_utils.py", "eagle_sample")
    assert "target_predict = torch.argmax(next_token_logits, dim=-1)" in sample
    assert "return predict, num_correct_drafts + 1, accept_index" in sample

    settle = function_source(
        ROOT / "source/batch_result_processor.py", "_resolve_spec_v2_tokens"
    )
    assert "accept_tokens = next_token_ids[" in settle
    assert "req.kv_committed_len += num_accept_tokens" in settle

    hybrid = function_source(ROOT / "source/hybrid_attn_backend.py", "_select_backend")
    assert "forward_mode.is_decode_or_idle()" in hybrid
    assert "forward_mode.is_target_verify()" in hybrid
    assert 'speculative_attention_mode == "decode"' in hybrid

    server_args = (ROOT / "source/server_args.py").read_text()
    assert "speculative_attention_mode" in server_args
    assert 'choices=["prefill", "decode"]' in server_args

    stock = json.loads(
        (
            RUNTIME / "artifacts/candidate-v0.5.15/inputs/ngram-launch.json"
        ).read_text()
    )["args"]
    candidate = json.loads(
        (ROOT / "inputs/decode_attention_launch.json").read_text()
    )["args"]
    assert candidate[:-2] == stock
    assert candidate[-2:] == ["--speculative-attention-mode", "decode"]

    result = {
        "schema_version": 1,
        "classification": "source_and_artifact_supported_target_verify_localization",
        "binding_verified": True,
        "checked_binding_paths": checked,
        "measured": {
            "first_divergence": mismatches[0],
            "all_preceding_emitted_tokens": 51935,
            "request_217_actual_run": [
                {"token": 51935, "count": 19},
                {"token": 3055, "count": 339},
            ],
            "request_217_bound_run": [{"token": 51935, "count": 358}],
            "other_divergences": mismatches[1:],
        },
        "source_derived": {
            "corpus_insert_tail": prompt_tail,
            "token_3055_absent_from_corpus_inputs_before_request_217": True,
            "token_3055_role": "target_verifier_bonus_not_ngram_proposal",
            "accepted_token_accounting": "accept_lens includes bonus; KV mover receives accept_lens-1; scheduler commits the full sliced accepted run",
            "request_ownership": "req_ids key stateful corpus lookup; req_pool_indices key accepted-KV movement; no observed neighboring request emitted token 3055",
            "stock_target_verify_attention_route": "prefill",
            "ordinary_decode_attention_route": "decode",
        },
        "inferred": {
            "causal_boundary": "target verification attention/numerical dataflow before greedy argmax",
            "not_yet_measured": "request-217 target-verify versus ordinary-decode logits, margins, and exact KV bytes",
        },
        "candidate": {
            "name": "decode_attention_target_verify",
            "delta": ["--speculative-attention-mode", "decode"],
            "semantics": "target-semantics preserving; target, drafts, greedy verifier, accounting, cache ownership, and request bytes unchanged",
            "falsifier": "first 218 requests at their bound arrivals; require all exact, zero failures, native NGRAM activation, and request 217 output token 19 equal to 51935",
        },
    }
    (ROOT / "LOCALIZATION.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
