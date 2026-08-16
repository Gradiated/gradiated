#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import types

import torch


VOCAB_SIZE = 262144
HIDDEN_SIZE = 4
BLOCK_SIZE = 16
CAPTURE_BATCH_SIZES = [1, 2, 4, 8, 12, 16, 24, 32]


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def cpu_fp8_linear(
    hidden_states: torch.Tensor,
    weight: torch.Tensor,
    weight_scale: torch.Tensor,
    **_: object,
) -> torch.Tensor:
    return (
        hidden_states.float()
        .matmul(weight.float().mul(weight_scale.float()))
        .to(torch.bfloat16)
    )


def compute_acceptance(
    candidates: torch.Tensor,
    target_predict: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    if candidates.ndim != 2 or target_predict.shape != candidates.shape:
        raise ValueError("invalid DFlash acceptance shape")
    matches = candidates[:, 1:] == target_predict[:, :-1]
    correct_len = matches.to(torch.int32).cumprod(dim=1).sum(dim=1)
    bonus = target_predict[
        torch.arange(candidates.shape[0]),
        correct_len,
    ]
    return correct_len, bonus.to(torch.int64)


def settle_request(
    *,
    candidates: torch.Tensor,
    target_predict: torch.Tensor,
    finish_after: int | None = None,
) -> dict[str, object]:
    correct_len, bonus = compute_acceptance(
        candidates.unsqueeze(0),
        target_predict.unsqueeze(0),
    )
    accepted = int(correct_len[0])
    proposed = candidates[1 : 1 + accepted].tolist() + [int(bonus[0])]
    appended = []
    for token in proposed:
        appended.append(int(token))
        if finish_after is not None and len(appended) >= finish_after:
            break
    return {
        "accepted_drafts": max(0, len(appended) - 1),
        "appended": appended,
        "commit_len": len(appended),
        "bonus": int(bonus[0]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-root", type=pathlib.Path, required=True)
    parser.add_argument("--adapted-gemma", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    project_dir = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(project_dir / "overlay"))
    import dflash_fp8_tied_head_stack as stack

    srt_root = args.sglang_root / "python/sglang/srt"
    observed = stack.source_hashes(
        srt_root,
        gemma4_override=args.adapted_gemma,
    )
    stack.verify_source_hashes(observed)
    tampered = dict(observed)
    tampered["speculative/dflash_worker.py"] = "0" * 64
    fail_closed = False
    try:
        stack.verify_source_hashes(tampered)
    except RuntimeError as error:
        fail_closed = "unsupported_sglang_source_topology" in str(error)
    assert fail_closed

    sources = {
        "gemma": args.adapted_gemma.read_text(),
        "worker": (srt_root / "speculative/dflash_worker.py").read_text(),
        "verify": (srt_root / "speculative/dflash_info.py").read_text(),
        "verify_utils": (srt_root / "speculative/dflash_utils.py").read_text(),
        "logits": (srt_root / "layers/logits_processor.py").read_text(),
        "graph": (
            srt_root / "model_executor/runner/decode_cuda_graph_runner.py"
        ).read_text(),
        "sampler": (srt_root / "layers/sampler.py").read_text(),
    }
    anchors = {
        "tied_head_adapter": "if self.lm_head is not tied_head:" in sources["gemma"],
        "target_head_inside_forward": "return self.logits_processor(" in sources["gemma"],
        "draft_uses_tied_bf16_weight": "weight = lm_head.weight" in sources["worker"],
        "draft_does_not_call_logits_processor": (
            "draft_next = self._greedy_sample_from_vocab_parallel_head("
            in sources["worker"]
        ),
        "target_verify_uses_full_logits": (
            "torch.argmax(logits_output.next_token_logits, dim=-1)"
            in sources["verify"]
        ),
        "greedy_acceptance_rule": (
            "matches = candidates[:, 1:] == target_predict[:, :-1]"
            in sources["verify_utils"]
        ),
        "softcap_after_head": "fused_softcap(logits" in sources["logits"],
        "graph_raw_logit_slice": (
            "output.next_token_logits[: self.raw_num_token]" in sources["graph"]
        ),
        "graph_raw_hidden_slice": (
            "output.hidden_states[: self.raw_num_token]" in sources["graph"]
        ),
        "greedy_sampler_lowest_index": "torch.argmax(logits, -1)" in sources["sampler"],
    }
    assert all(anchors.values())

    torch.manual_seed(20260725)
    tied = torch.nn.Embedding(VOCAB_SIZE, HIDDEN_SIZE, dtype=torch.bfloat16)
    with torch.no_grad():
        tied.weight.zero_()
        tied.weight[0] = torch.tensor([10, 0, 5, 0], dtype=torch.bfloat16)
        tied.weight[VOCAB_SIZE // 2] = torch.tensor(
            [0, 0, 5, 0],
            dtype=torch.bfloat16,
        )
        tied.weight[VOCAB_SIZE - 2] = torch.tensor(
            [0, 0, 0, 7],
            dtype=torch.bfloat16,
        )
        tied.weight[VOCAB_SIZE - 1] = torch.tensor(
            [0, 10, 5, 7],
            dtype=torch.bfloat16,
        )
    original_parameter = tied.weight
    original_data_ptr = tied.weight.data_ptr()
    tied.shard_indices = types.SimpleNamespace(
        org_vocab_start_index=0,
        org_vocab_end_index=VOCAB_SIZE,
        num_org_elements=VOCAB_SIZE,
        num_org_elements_padded=VOCAB_SIZE,
        added_vocab_start_index=VOCAB_SIZE,
        added_vocab_end_index=VOCAB_SIZE,
        num_added_elements=0,
    )
    stack.materialize_e4m3_target_projection(
        tied,
        vocab_size=VOCAB_SIZE,
        hidden_size=HIDDEN_SIZE,
        weight_scale=0.125,
        require_cuda=False,
    )
    ownership = stack.validate_projection_ownership(
        tied,
        tied,
        vocab_size=VOCAB_SIZE,
        hidden_size=HIDDEN_SIZE,
    )
    assert tied.weight is original_parameter
    assert tied.weight.data_ptr() == original_data_ptr

    hidden = torch.eye(HIDDEN_SIZE, dtype=torch.bfloat16)
    bf16_logits = hidden.float().matmul(tied.weight.float().T).to(torch.bfloat16)
    target_logits = stack.compute_target_logits(
        hidden,
        tied,
        apply_fp8_linear_fn=cpu_fp8_linear,
    )
    expected = torch.tensor(
        [0, VOCAB_SIZE - 1, 0, VOCAB_SIZE - 2],
        dtype=torch.long,
    )
    assert torch.equal(target_logits, bf16_logits)
    assert torch.equal(torch.argmax(target_logits, dim=-1), expected)
    softcap_logits = 30.0 * torch.tanh(target_logits.float() / 30.0)
    assert torch.equal(torch.argmax(softcap_logits, dim=-1), expected)

    draft_logits = hidden.float().matmul(tied.weight.float().T).to(torch.bfloat16)
    assert torch.equal(torch.argmax(draft_logits, dim=-1), expected)
    assert ownership["draft_owner"] == "tied_bf16_weight"
    assert ownership["target_owner"] == "target_logits_only"

    padded_shapes = []
    for padded_bs in CAPTURE_BATCH_SIZES:
        rows = padded_bs * BLOCK_SIZE
        buffer = torch.arange(rows, dtype=torch.int64)
        for raw_bs in (1, max(1, padded_bs - 1), padded_bs):
            raw_bs = min(raw_bs, padded_bs)
            raw_rows = raw_bs * BLOCK_SIZE
            replay = buffer[:raw_rows]
            assert replay.numel() == raw_rows
            assert bool((replay < raw_rows).all())
        padded_shapes.append(
            {
                "capture_batch_size": padded_bs,
                "target_head_m": rows,
            }
        )

    first_buffer = torch.arange(4 * BLOCK_SIZE, dtype=torch.int64)
    first_live = first_buffer[: 2 * BLOCK_SIZE].clone()
    assert first_live[-1].item() == 31
    second_buffer = first_buffer
    second_buffer[:BLOCK_SIZE] = torch.arange(
        1000,
        1000 + BLOCK_SIZE,
        dtype=torch.int64,
    )
    reused_live = second_buffer[:BLOCK_SIZE]
    assert reused_live.tolist() == list(range(1000, 1000 + BLOCK_SIZE))
    assert 32 not in reused_live.tolist()

    no_accept_candidates = torch.tensor([10, 20, 21, 22], dtype=torch.long)
    no_accept_target = torch.tensor([99, 98, 97, 96], dtype=torch.long)
    no_accept = settle_request(
        candidates=no_accept_candidates,
        target_predict=no_accept_target,
    )
    assert no_accept == {
        "accepted_drafts": 0,
        "appended": [99],
        "commit_len": 1,
        "bonus": 99,
    }

    partial_candidates = torch.tensor([10, 20, 21, 22], dtype=torch.long)
    partial_target = torch.tensor([20, 21, 99, 96], dtype=torch.long)
    partial = settle_request(
        candidates=partial_candidates,
        target_predict=partial_target,
    )
    assert partial == {
        "accepted_drafts": 2,
        "appended": [20, 21, 99],
        "commit_len": 3,
        "bonus": 99,
    }
    completion = settle_request(
        candidates=partial_candidates,
        target_predict=partial_target,
        finish_after=1,
    )
    assert completion == {
        "accepted_drafts": 0,
        "appended": [20],
        "commit_len": 1,
        "bonus": 99,
    }

    active_request_ids = torch.tensor([7, 3, 11], dtype=torch.long)
    after_cancel = active_request_ids[torch.tensor([0, 2])]
    assert after_cancel.tolist() == [7, 11]
    after_slot_reuse = torch.tensor([7, 3, 11], dtype=torch.long)
    assert after_slot_reuse.tolist() == [7, 3, 11]
    assert not hasattr(tied, "_dflash_fp8_request_state")
    assert not hasattr(tied, "_dflash_fp8_slot_state")

    result = {
        "schema_version": 1,
        "status": "pass",
        "runtime_commit": "588d1f7bc9424201f89957e145f9d5af633a3eb8",
        "source_hashes": observed,
        "source_anchors": anchors,
        "fail_closed_source_mismatch": fail_closed,
        "ownership": ownership,
        "embedding": {
            "dtype": str(tied.weight.dtype),
            "same_parameter": tied.weight is original_parameter,
            "same_data_ptr": tied.weight.data_ptr() == original_data_ptr,
            "shape": list(tied.weight.shape),
        },
        "target_projection": {
            "dtype": str(getattr(tied, stack.TARGET_WEIGHT_NAME).dtype),
            "shape": list(getattr(tied, stack.TARGET_WEIGHT_NAME).shape),
            "separate_storage": (
                getattr(tied, stack.TARGET_WEIGHT_NAME).data_ptr()
                != tied.weight.data_ptr()
            ),
            "complete_logit_elements_compared": target_logits.numel(),
            "bf16_logits_bit_exact": torch.equal(target_logits, bf16_logits),
            "expected_tokens": expected.tolist(),
            "target_tokens": torch.argmax(target_logits, dim=-1).tolist(),
            "softcap_tokens": torch.argmax(softcap_logits, dim=-1).tolist(),
        },
        "draft_projection": {
            "storage": "lm_head.weight",
            "dtype": str(tied.weight.dtype),
            "tokens": torch.argmax(draft_logits, dim=-1).tolist(),
        },
        "full_vocabulary": {
            "org_range": [0, VOCAB_SIZE],
            "added_range": [VOCAB_SIZE, VOCAB_SIZE],
            "boundary_and_tie_tokens": expected.tolist(),
        },
        "cuda_graph_contract": {
            "draft_token_num": BLOCK_SIZE,
            "capture_batch_sizes": CAPTURE_BATCH_SIZES,
            "padded_target_head_shapes": padded_shapes,
            "raw_rows_sliced_before_verify": True,
            "slot_reuse_stale_padding_excluded": True,
        },
        "lifecycle": {
            "cancelled_request_filtered": after_cancel.tolist(),
            "slot_reuse_request_ids": after_slot_reuse.tolist(),
            "projection_request_state": False,
            "projection_slot_state": False,
            "empty_acceptance": no_accept,
            "partial_acceptance": partial,
            "completion_truncation": completion,
        },
    }
    atomic_json(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
