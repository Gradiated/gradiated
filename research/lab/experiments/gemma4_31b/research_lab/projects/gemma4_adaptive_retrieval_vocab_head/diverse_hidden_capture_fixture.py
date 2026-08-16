from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass

import torch

from diverse_hidden_capture_hook import (
    CaptureConfig,
    PINNED_GEMMA4_CAUSAL_SHA256,
    PINNED_LOGITS_PROCESSOR_SHA256,
    TargetVerifyHiddenCapture,
    install_logits_processor_capture,
    sha256_file,
)


PROJECT = pathlib.Path(__file__).resolve().parent
PINNED_PROJECT = PROJECT.parent / "gemma4_h200_ngram_decode_equivalent_verifier"
PINNED_SOURCES = {
    "gemma4_causal.py": PINNED_PROJECT / "inputs/source/gemma4_causal.py",
    "logits_processor.py": PINNED_PROJECT / "inputs/source/logits_processor.py",
    "forward_batch_info.py": PINNED_PROJECT / "inputs/source/forward_batch_info.py",
}


class TargetVerifyMode:
    def is_target_verify(self) -> bool:
        return True


class DecodeMode:
    def is_target_verify(self) -> bool:
        return False


@dataclass
class SpecInfo:
    draft_token_num: int


@dataclass
class ForwardBatch:
    forward_mode: object
    spec_info: SpecInfo
    req_pool_indices: torch.Tensor
    rids: list[str]
    rids_int: torch.Tensor
    positions: torch.Tensor


class FakeLogitsProcessor:
    def forward(
        self,
        input_ids: torch.Tensor,
        hidden_states: torch.Tensor,
        lm_head: torch.Tensor,
        logits_metadata: ForwardBatch,
    ) -> torch.Tensor:
        self.last_hidden_data_ptr = hidden_states.data_ptr()
        return hidden_states @ lm_head.T


def sha256_tensor(tensor: torch.Tensor) -> str:
    return hashlib.sha256(tensor.contiguous().view(torch.uint8).numpy()).hexdigest()


def acceptance(logits: torch.Tensor, proposals: torch.Tensor) -> torch.Tensor:
    return torch.argmax(logits, dim=-1).to(torch.int32).eq(proposals)


def run(output: pathlib.Path, terminal: pathlib.Path) -> dict:
    torch.manual_seed(20260726)
    request_count = 3
    depth_count = 4
    hidden_width = 8
    vocab_size = 19
    rows = request_count * depth_count

    row = torch.arange(rows, dtype=torch.float32).unsqueeze(1)
    coordinate = torch.arange(hidden_width, dtype=torch.float32).unsqueeze(0)
    hidden = torch.sin(row * 0.37 + coordinate * 0.19) + row * 0.031
    weight = torch.cos(
        torch.arange(vocab_size * hidden_width, dtype=torch.float32).reshape(
            vocab_size, hidden_width
        )
        * 0.071
    )
    proposals = torch.argmax(hidden @ weight.T, dim=-1).to(torch.int32)
    proposals[1::3] = (proposals[1::3] + 1) % vocab_size
    batch = ForwardBatch(
        forward_mode=TargetVerifyMode(),
        spec_info=SpecInfo(draft_token_num=depth_count),
        req_pool_indices=torch.tensor([41, 7, 93], dtype=torch.int32),
        rids=["request-alpha", "request-beta", "request-gamma"],
        rids_int=torch.tensor([100901, 100117, 100733], dtype=torch.int64),
        positions=torch.tensor(
            [400, 401, 402, 403, 811, 812, 813, 814, 1205, 1206, 1207, 1208],
            dtype=torch.int32,
        ),
    )

    control_processor = FakeLogitsProcessor()
    control_logits = control_processor.forward(proposals, hidden, weight, batch)
    control_acceptance = acceptance(control_logits, proposals)
    capture = TargetVerifyHiddenCapture(
        CaptureConfig(
            destination=output,
            audit=output.with_suffix(".audit.jsonl"),
            maximum_rows=rows,
            expected_hidden_width=hidden_width,
            require_eager=True,
        )
    )
    original = install_logits_processor_capture(FakeLogitsProcessor, capture)
    candidate_processor = FakeLogitsProcessor()
    candidate_logits = candidate_processor.forward(proposals, hidden, weight, batch)
    candidate_acceptance = acceptance(candidate_logits, proposals)

    payload = torch.load(output, weights_only=False)
    captured_hidden = payload["hidden_states"]
    consumer_logits = captured_hidden @ weight.T
    consumer_acceptance = acceptance(
        consumer_logits, payload["proposal_token_ids"]
    )
    expected_ownership = [
        {
            "global_row": index,
            "capture_index": 0,
            "capture_row": index,
            "request_batch_index": index // depth_count,
            "request_pool_index": [41, 7, 93][index // depth_count],
            "request_id": [
                "request-alpha",
                "request-beta",
                "request-gamma",
            ][index // depth_count],
            "request_id_int": [100901, 100117, 100733][index // depth_count],
            "depth_index": index % depth_count,
        }
        for index in range(rows)
    ]

    before_non_target = capture.row_count
    non_target_batch = ForwardBatch(
        forward_mode=DecodeMode(),
        spec_info=SpecInfo(draft_token_num=depth_count),
        req_pool_indices=batch.req_pool_indices,
        rids=batch.rids,
        rids_int=batch.rids_int,
        positions=batch.positions,
    )
    candidate_processor.forward(proposals, hidden, weight, non_target_batch)
    after_non_target = capture.row_count
    FakeLogitsProcessor.forward = original

    failing_capture = TargetVerifyHiddenCapture(
        CaptureConfig(
            destination=output.with_name("must-not-be-written.pt"),
            audit=output.with_suffix(".audit.jsonl"),
            maximum_rows=rows,
            expected_hidden_width=hidden_width + 1,
            require_eager=True,
        )
    )
    failure_original = install_logits_processor_capture(
        FakeLogitsProcessor, failing_capture
    )
    failure_processor = FakeLogitsProcessor()
    failure_isolated_logits = failure_processor.forward(
        proposals, hidden, weight, batch
    )
    FakeLogitsProcessor.forward = failure_original

    checks = {
        "same_hidden_storage_seen_by_original_consumer": (
            control_processor.last_hidden_data_ptr
            == candidate_processor.last_hidden_data_ptr
            == hidden.data_ptr()
        ),
        "control_candidate_logits_bitwise_equal": torch.equal(
            control_logits, candidate_logits
        ),
        "control_candidate_acceptance_bitwise_equal": torch.equal(
            control_acceptance, candidate_acceptance
        ),
        "capture_consumer_logits_bitwise_equal": torch.equal(
            control_logits, consumer_logits
        ),
        "capture_consumer_acceptance_bitwise_equal": torch.equal(
            control_acceptance, consumer_acceptance
        ),
        "ownership_exact": payload["ownership"] == expected_ownership,
        "non_target_ignored": before_non_target == after_non_target == rows,
        "hidden_rows_exact": torch.equal(hidden, captured_hidden),
        "proposal_rows_exact": torch.equal(
            proposals, payload["proposal_token_ids"]
        ),
        "observer_failure_isolated": torch.equal(
            control_logits, failure_isolated_logits
        )
        and failure_processor.last_hidden_data_ptr == hidden.data_ptr()
        and not output.with_name("must-not-be-written.pt").exists(),
    }
    if not all(checks.values()):
        raise RuntimeError(f"fixture_check_failed:{checks}")

    pinned_hashes = {
        name: sha256_file(path) for name, path in PINNED_SOURCES.items()
    }
    if pinned_hashes["gemma4_causal.py"] != PINNED_GEMMA4_CAUSAL_SHA256:
        raise RuntimeError("pinned_gemma_source_changed")
    if pinned_hashes["logits_processor.py"] != PINNED_LOGITS_PROCESSOR_SHA256:
        raise RuntimeError("pinned_logits_source_changed")

    project_path = str(PROJECT)
    capture_root = (
        project_path + "/artifacts/exact-diverse-c32-target-verify"
    )
    later_command = (
        "env "
        f"PYTHONPATH={project_path}/capture_bootstrap:{project_path} "
        f"DIVERSE_HIDDEN_CAPTURE_PATH={capture_root}/hidden_states.pt "
        f"DIVERSE_HIDDEN_CAPTURE_AUDIT={capture_root}/audit.jsonl "
        "DIVERSE_HIDDEN_CAPTURE_MAX_ROWS=1536 "
        "DIVERSE_HIDDEN_CAPTURE_EXPECTED_WIDTH=5376 "
        "DIVERSE_HIDDEN_CAPTURE_REQUIRE_EAGER=1 "
        "python3 /work/input/endpoint_entrypoint.py "
        "--model-path /work/checkpoint --tokenizer-path /work/checkpoint "
        "--served-model-name google/gemma-4-31B-it --dtype bfloat16 "
        "--quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 "
        "--host 0.0.0.0 --context-length 5000 --max-running-requests 32 "
        "--mem-fraction-static 0.85 --enable-metrics --skip-server-warmup "
        "--enable-dynamic-chunking --chunked-prefill-size 2048 "
        "--enable-fused-qk-norm-rope --prefill-attention-backend triton "
        "--decode-attention-backend triton --page-size 1 "
        "--num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8 "
        "--tool-call-parser gemma4 --port 30000 "
        "--speculative-algorithm NGRAM --disable-cuda-graph"
    )
    result = {
        "schema_version": 1,
        "status": "pass",
        "decision": "exact_diverse_capture_hook_ready_for_later_bound_capture",
        "scientific_scope": "synthetic producer-to-consumer contract only; no model-quality or performance claim",
        "exact_path": {
            "producer": "sglang.srt.models.gemma4_causal.Gemma4TextModel.forward",
            "boundary": "Gemma4ForCausalLM.forward hidden_states argument passed unchanged into LogitsProcessor.forward",
            "hook": "sglang.srt.layers.logits_processor.LogitsProcessor.forward entry",
            "tied_head_consumer": "LogitsProcessor._get_logits -> _compute_lm_head",
            "graph_policy": "later one-shot capture explicitly disables CUDA graphs so Python observes live verifier rows rather than graph-capture placeholders",
        },
        "source_hashes": {
            **pinned_hashes,
            "diverse_hidden_capture_hook.py": sha256_file(
                PROJECT / "diverse_hidden_capture_hook.py"
            ),
            "capture_bootstrap/sitecustomize.py": sha256_file(
                PROJECT / "capture_bootstrap/sitecustomize.py"
            ),
            "diverse_hidden_capture_fixture.py": sha256_file(pathlib.Path(__file__)),
        },
        "ownership_schema": {
            "layout": payload["layout"],
            "fields": list(expected_ownership[0]),
            "request_identity": "request_id_int plus request_pool_index",
            "row_identity": "global_row, capture_index, capture_row",
            "depth_identity": "zero-based depth_index within request-major NGRAM rows",
        },
        "fixture": {
            "request_count": request_count,
            "depth_count": depth_count,
            "rows": rows,
            "hidden_width": hidden_width,
            "unique_hidden_rows": int(torch.unique(hidden, dim=0).shape[0]),
            "accepted_rows": int(control_acceptance.sum().item()),
            "rejected_rows": int((~control_acceptance).sum().item()),
            "hidden_sha256": sha256_tensor(hidden),
            "logits_sha256": sha256_tensor(control_logits),
            "acceptance_sha256": sha256_tensor(control_acceptance),
            "capture_path": str(output.relative_to(PROJECT)),
            "capture_sha256": sha256_file(output),
            "checks": checks,
        },
        "noninterference": {
            "hidden_tensor_returned_or_substituted": False,
            "original_consumer_called_with_original_hidden_states": True,
            "logits_bitwise_equal": True,
            "acceptance_bitwise_equal": True,
            "observer_errors_are_audited_and_do_not_skip_original_consumer": True,
        },
        "exact_later_capture_command": later_command,
        "later_capture_preconditions": [
            "Materialize the pinned endpoint_entrypoint.py and exact workload runner under this project before any future bench claim.",
            "Verify the installed gemma4_causal.py and logits_processor.py hashes recorded above.",
            "Run the exact c32 request producer against port 30000 while this server command is active.",
            "Do not use CUDA graphs for this one-shot evidence capture; re-enable them for performance measurements.",
        ],
        "resource_use": {
            "gpu_claimed": False,
            "ssh_used": False,
            "provider_mutation": False,
            "paid_requests": 0,
        },
    }
    terminal.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=PROJECT / "artifacts/diverse-hidden-capture-fixture/capture.pt",
    )
    parser.add_argument(
        "--terminal",
        type=pathlib.Path,
        default=PROJECT / "DIVERSE_HIDDEN_CAPTURE_HOOK_TERMINAL.json",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = run(args.output.resolve(), args.terminal.resolve())
    print(
        json.dumps(
            {
                "status": result["status"],
                "rows": result["fixture"]["rows"],
                "unique_hidden_rows": result["fixture"]["unique_hidden_rows"],
                "terminal": str(args.terminal),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
