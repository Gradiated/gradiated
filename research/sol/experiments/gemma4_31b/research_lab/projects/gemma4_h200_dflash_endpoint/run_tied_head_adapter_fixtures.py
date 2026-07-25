#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import pathlib
import types

import torch

import sglang.srt.models.gemma4_mm as gemma4_mm
import sglang.srt.speculative.dflash_worker as dflash_worker


VOCAB_SIZE = 262144
HIDDEN_SIZE = 4


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def init_worker() -> object:
    worker = object.__new__(dflash_worker.DFlashWorker)
    for name in (
        "_draft_greedy_gathered_max_buf",
        "_draft_greedy_gathered_ids_buf",
        "_draft_greedy_local_max_buf",
        "_draft_greedy_local_arg_buf",
        "_draft_greedy_best_rank_buf",
        "_draft_greedy_rank_index_buf",
        "_draft_greedy_selected_ids_buf",
    ):
        setattr(worker, name, None)
    for name in (
        "_draft_greedy_gather_cap",
        "_draft_greedy_local_cap",
        "_draft_greedy_index_cap",
    ):
        setattr(worker, name, 0)
    return worker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    gemma4_mm.get_tensor_model_parallel_world_size = lambda: 1
    dflash_worker.get_tp_group = lambda: types.SimpleNamespace(world_size=1)

    torch.manual_seed(20260725)
    embedding = torch.nn.Embedding(VOCAB_SIZE, HIDDEN_SIZE, dtype=torch.bfloat16)
    with torch.no_grad():
        embedding.weight.uniform_(-0.01, 0.01)
        embedding.weight[0] = torch.tensor([10, 0, 5, 0], dtype=torch.bfloat16)
        embedding.weight[VOCAB_SIZE // 2] = torch.tensor(
            [0, 0, 5, 0], dtype=torch.bfloat16
        )
        embedding.weight[VOCAB_SIZE - 2] = torch.tensor(
            [0, 0, 0, 7], dtype=torch.bfloat16
        )
        embedding.weight[VOCAB_SIZE - 1] = torch.tensor(
            [0, 10, 5, 7], dtype=torch.bfloat16
        )

    original_parameter = embedding.weight
    original_data_ptr = embedding.weight.data_ptr()
    adapter = gemma4_mm.bind_tp1_tied_embedding_dflash_head(
        embedding, VOCAB_SIZE
    )
    shard = adapter.shard_indices

    hidden_states = torch.tensor(
        [
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ],
        dtype=torch.bfloat16,
    )
    with torch.inference_mode():
        reference_logits = torch.matmul(hidden_states, embedding.weight.T)
        adapted_logits = torch.matmul(
            hidden_states, adapter.weight[: shard.num_org_elements].T
        )
        reference_tokens = torch.argmax(reference_logits, dim=-1)
        consumer_tokens = (
            dflash_worker.DFlashWorker._greedy_sample_from_vocab_parallel_head(
                init_worker(),
                hidden_states=hidden_states,
                lm_head=adapter,
                chunk_size=2,
            )
        )

    expected_tokens = torch.tensor(
        [0, VOCAB_SIZE - 1, 0, VOCAB_SIZE - 2], dtype=torch.long
    )
    assert adapter is embedding
    assert adapter.weight is original_parameter
    assert adapter.weight.data_ptr() == original_data_ptr
    assert torch.equal(reference_logits, adapted_logits)
    assert torch.equal(reference_tokens, expected_tokens)
    assert torch.equal(consumer_tokens, expected_tokens)
    assert shard.org_vocab_start_index == 0
    assert shard.org_vocab_end_index == VOCAB_SIZE
    assert shard.num_org_elements == VOCAB_SIZE
    assert shard.num_org_elements_padded == VOCAB_SIZE
    assert shard.num_added_elements == 0
    assert shard.added_vocab_start_index == VOCAB_SIZE
    assert shard.added_vocab_end_index == VOCAB_SIZE

    bound_model = types.SimpleNamespace(
        pp_group=types.SimpleNamespace(world_size=1),
        language_model=types.SimpleNamespace(
            embed_tokens=embedding,
            layers_to_capture=None,
        ),
        lm_head=embedding,
        vocab_size=VOCAB_SIZE,
        capture_aux_hidden_states=False,
    )
    capture_layer_ids = [1, 12, 23, 35, 46, 57]
    gemma4_mm.Gemma4ForConditionalGeneration.set_dflash_layers_to_capture(
        bound_model, capture_layer_ids
    )
    assert bound_model.capture_aux_hidden_states is True
    assert bound_model.language_model.layers_to_capture == [
        value + 1 for value in capture_layer_ids
    ]
    assert bound_model.lm_head is bound_model.language_model.embed_tokens
    assert bound_model.lm_head.shard_indices is not None

    gemma4_mm.get_tensor_model_parallel_world_size = lambda: 2
    tp_guard_passed = False
    try:
        gemma4_mm.bind_tp1_tied_embedding_dflash_head(embedding, VOCAB_SIZE)
    except ValueError as error:
        tp_guard_passed = "requires TP=1" in str(error)
    assert tp_guard_passed

    consumer_source = inspect.getsource(
        dflash_worker.DFlashWorker._greedy_sample_from_vocab_parallel_head
    ).encode()
    adapter_source = inspect.getsource(
        gemma4_mm.bind_tp1_tied_embedding_dflash_head
    ).encode()
    result = {
        "schema_version": 1,
        "status": "pass",
        "runtime_commit": "588d1f7bc9424201f89957e145f9d5af633a3eb8",
        "fixture": {
            "dtype": "bfloat16",
            "vocab_size": VOCAB_SIZE,
            "hidden_size": HIDDEN_SIZE,
            "complete_logit_elements_compared": reference_logits.numel(),
            "complete_logits_bit_exact": True,
            "expected_tokens": expected_tokens.tolist(),
            "consumer_tokens": consumer_tokens.tolist(),
            "fixtures": [
                "lowest_vocabulary_boundary",
                "highest_vocabulary_boundary",
                "nonadjacent_lowest_index_tie",
                "adjacent_high_boundary_tie",
            ],
        },
        "adapter": {
            "same_module": True,
            "same_parameter": True,
            "same_data_ptr": True,
            "capture_hook_binding_invoked": True,
            "capture_layer_ids": capture_layer_ids,
            "internal_capture_layer_ids": (
                bound_model.language_model.layers_to_capture
            ),
            "weight_shape": list(adapter.weight.shape),
            "org_vocab_range": [
                shard.org_vocab_start_index,
                shard.org_vocab_end_index,
            ],
            "added_vocab_range": [
                shard.added_vocab_start_index,
                shard.added_vocab_end_index,
            ],
            "tp2_rejected": tp_guard_passed,
            "source_sha256": sha256_bytes(adapter_source),
        },
        "consumer": {
            "module": "sglang.srt.speculative.dflash_worker.DFlashWorker",
            "method": "_greedy_sample_from_vocab_parallel_head",
            "source_sha256": sha256_bytes(consumer_source),
            "actual_pinned_consumer_invoked": True,
        },
    }
    atomic_json(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
