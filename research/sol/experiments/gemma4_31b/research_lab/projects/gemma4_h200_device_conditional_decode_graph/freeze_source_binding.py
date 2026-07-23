from __future__ import annotations

import hashlib
import json
import pathlib
import sys


PROJECT = pathlib.Path(__file__).resolve().parent
UPSTREAM = PROJECT / "inputs" / "upstream"
CURRENT_STACK = PROJECT / "inputs" / "current_stack"
COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"

EXPECTED_UPSTREAM = {
    "layers/attention/triton_backend.py": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
    "layers/sampler.py": "85541951e1cf50d10c54978178e403ff9d4aa6f223e629ea91965735ba882a8f",
    "managers/schedule_batch.py": "eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874",
    "managers/scheduler.py": "3a26deea85f43d61c27b94013288ad95d6ee75111fe40134893541777c9c8cd4",
    "managers/scheduler_components/batch_result_processor.py": "9c764afffb106e966fde110851de73bb6a3d0f2415343a574a255e91f86851de",
    "managers/tp_worker.py": "f2e00ea7d53b7250231d44b9d52415c6f6b5f936b0e7c6af4a13f5aff6c1e509",
    "model_executor/cuda_graph_runner.py": "7d1898247e80ff6a446eb42e4968d2eea0df30b109ee2d089a9ad78791bc079e",
    "model_executor/forward_batch_info.py": "c977296f3b90be69fff5312f2b3af7699a17b20af24614b139f69888e5776516",
    "model_executor/model_runner.py": "f4dad073eb9f89afd4cda0439b97dee63f8de131d0ed10078b817dba1f978f59",
    "sampling/penaltylib/orchestrator.py": "88d9a4c04866a8b2dad0efe6f010f28f7e7dfa0e65708920f7845d760e833192",
    "sampling/sampling_batch_info.py": "e7903417a4cab05294975d069555987e2720557dd9fd0b8d79a6f934f3fbb0db",
}

EXPECTED_STACK = {
    "AUTHORITATIVE_QKV_TERMINAL.json": "1b563ea1dd933d097a337b33fb17dc13601ded1689597071c8f6fd9e74f17912",
    "FP8_QKV_INPUT_MANIFEST.json": "d999420ebd05dacd0e15cf08aad34f6a68b657367bf6dc28c4738df0d0663586",
    "attention_intervention.py": "4e11a14e2dc149789a4b4350e02de3d3283ad88fc259d6417f05a734fc1451d8",
    "bound_remote_fp8_stack.sh": "f6c80216e29b426811badea59e6e148629d0f5b951efa0e314b04ae19c5b5ffc",
    "bound_stack_sitecustomize.py": "5791f6718b90b1ac555f7cb53179b18fd523ffb9f469d02582482431623d39fa",
    "fp8_qkv_paired_runner.py": "143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7",
    "host_min_new_tokens_gate.py": "2779aae2c51c63ef3119edff9b57e39f09576975ec6e15fb66928e6069405c2a",
    "install_endpoint_patch.py": "71498993e844295a313d71620661361304203a26bb8a876d8da02d49f7fe7588",
    "pinned_async_penalty_tokens.py": "58f4c65846af62ad21aeb765d7764686c364335d29fff45eac65da86ab296197",
    "proven_v0513_endpoint_entrypoint.py": "b4a43f799499b4624d448ff5a8ef52e88bd4c3544fd0878ee5adcd3a1926d6fc",
    "proven_v0513_paired_endpoint_runner.py": "df65b1e49c941c27a975ecb1f2d34041a0e63695c2e3515cf950406204f614f3",
    "qkv_epilogue_discriminator.py": "0f9c58b04ec0201e8b0a0dee1e3faab63643e3ded6c01ec7507456ccfb35b86d",
    "residual_intervention.py": "9b5a51284ac313014988f426c35b818ae2590cb7d4a72ec604a6ad80a63336b3",
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: pathlib.Path, expected: dict[str, str]) -> list[dict[str, object]]:
    rows = []
    for relative, expected_hash in expected.items():
        path = root / relative
        actual = sha256(path)
        if actual != expected_hash:
            raise RuntimeError(f"{relative}: expected {expected_hash}, found {actual}")
        rows.append(
            {
                "path": str(path.relative_to(PROJECT)),
                "sha256": actual,
                "bytes": path.stat().st_size,
            }
        )
    return rows


def require(source: str, tokens: list[str], label: str) -> None:
    missing = [token for token in tokens if token not in source]
    if missing:
        raise RuntimeError(f"{label} missing source tokens: {missing}")


def main() -> int:
    output = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "OFFLINE_SOURCE_BINDING.json"
    upstream_rows = verify(UPSTREAM, EXPECTED_UPSTREAM)
    stack_rows = verify(CURRENT_STACK, EXPECTED_STACK)

    cuda_graph = (UPSTREAM / "model_executor/cuda_graph_runner.py").read_text()
    worker = (UPSTREAM / "managers/tp_worker.py").read_text()
    scheduler = (UPSTREAM / "managers/scheduler.py").read_text()
    schedule_batch = (UPSTREAM / "managers/schedule_batch.py").read_text()
    result_processor = (
        UPSTREAM / "managers/scheduler_components/batch_result_processor.py"
    ).read_text()

    require(
        cuda_graph,
        [
            "def run_once():",
            "logits_output_or_pp_proxy_tensors = forward(",
            "self.graphs[graph_key].replay()",
        ],
        "cuda_graph_runner",
    )
    require(
        worker,
        [
            "out = self.model_runner.forward(",
            "batch_result.next_token_ids = self.model_runner.sample(",
        ],
        "tp_worker",
    )
    require(
        scheduler,
        [
            "result = self.run_batch(batch)",
            "self.process_batch_result(batch, result)",
            "batch.prepare_for_decode()",
        ],
        "scheduler",
    )
    require(
        schedule_batch,
        [
            "self.out_cache_loc = alloc_for_decode(self, token_per_req=1)",
            "req.decode_batch_idx += 1",
            "req.kv_committed_len += 1",
        ],
        "schedule_batch",
    )
    require(
        result_processor,
        [
            "next_token_ids = next_token_ids.tolist()",
            "req.output_ids.append(next_token_id)",
            "req.update_finish_state(new_accepted_len)",
        ],
        "batch_result_processor",
    )

    binding = {
        "schema_version": 1,
        "status": "offline_source_bound",
        "runtime": {
            "repository": "sgl-project/sglang",
            "commit": COMMIT,
            "image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
        },
        "candidate": {
            "repeat_tokens": 4,
            "continuation_owner": "device",
            "host_continuous_decode_flag": False,
            "schedule_stream_snapshot": False,
        },
        "source_contract": {
            "captured_body": "CudaGraphRunner.capture_one_batch_size.run_once -> model.forward",
            "sampling_boundary": "TPWorker.forward_batch_generation calls ModelRunner.sample after ModelRunner.forward returns",
            "host_result_boundary": "BatchResultProcessor._normalize_decode_outputs calls Tensor.tolist before request state and finish/EOS updates",
            "host_next_step_boundary": "Scheduler.update_running_batch -> ScheduleBatch.prepare_for_decode allocates the next KV slot and updates request counters",
            "conditional_graph_integration_requirement": "A valid candidate must replace all three post-forward host boundaries with graph-captured device state for four fixed iterations; a conditional-node smoke alone is insufficient.",
        },
        "upstream_files": upstream_rows,
        "current_stack_files": stack_rows,
        "project_local_snapshot": True,
        "pass": True,
    }
    output.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "pass": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
