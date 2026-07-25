#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parent
BINDING_PATH = ROOT / "DIRECTOR_BINDING.json"
SOURCE_ROOT = (
    ROOT
    / "../gemma4_h100_v0515_ngram_price_normalized/packet/candidate-v0.5.15/source/python/sglang/srt"
).resolve()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def lines_with(path: Path, needles: tuple[str, ...]) -> dict[str, list[int]]:
    lines = path.read_text().splitlines()
    result = {}
    for needle in needles:
        matches = [index for index, line in enumerate(lines, 1) if needle in line]
        if not matches:
            raise RuntimeError(f"source_anchor_missing:{path}:{needle}")
        result[needle] = matches
    return result


def main() -> None:
    binding_bytes = BINDING_PATH.read_bytes()
    binding = json.loads(binding_bytes)
    verified = []
    for name, item in binding["bound_inputs"].items():
        path = (ROOT / item["path"]).resolve()
        actual = sha256(path)
        verified.append(
            {
                "name": name,
                "path": str(path),
                "expected_sha256": item["sha256"],
                "actual_sha256": actual,
                "match": actual == item["sha256"],
            }
        )
    binding_result = {
        "schema_version": 1,
        "binding_path": str(BINDING_PATH),
        "binding_sha256": sha256_bytes(binding_bytes),
        "expected_binding_sha256": "bf640623c908f9273c24d6af04be10f3e7cf2a28738ff80f287d83f21ca98ddb",
        "binding_match": sha256_bytes(binding_bytes)
        == "bf640623c908f9273c24d6af04be10f3e7cf2a28738ff80f287d83f21ca98ddb",
        "bound_inputs": verified,
        "all_match": all(row["match"] for row in verified),
    }
    if not binding_result["all_match"] or not binding_result["binding_match"]:
        raise RuntimeError("director_binding_mismatch")
    atomic_json(ROOT / "DIRECTOR_BINDING_VERIFIED.json", binding_result)

    compact_path = Path(
        next(
            row["path"]
            for row in verified
            if row["name"] == "prior_h200_negative_compact"
        )
    )
    compact_members = {}
    with tarfile.open(compact_path, "r:gz") as archive:
        for name in (
            "out/FINAL_TERMINAL.json",
            "out/COMPONENT_TERMINAL.json",
            "out/ADAPTIVE_DEPTH_PATCH_STATE.json",
            "candidate/adaptive_depth.py",
        ):
            member = archive.extractfile(name)
            if member is None:
                raise RuntimeError(f"compact_member_missing:{name}")
            value = member.read()
            compact_members[name] = {
                "sha256": sha256_bytes(value),
                "bytes": len(value),
                "value": (
                    json.loads(value)
                    if name.endswith(".json")
                    else value.decode()
                ),
            }

    final_terminal = compact_members["out/FINAL_TERMINAL.json"]["value"]
    component = final_terminal["component"]
    comparisons = component["comparisons"]
    h200_patch = compact_members["candidate/adaptive_depth.py"]["value"]
    patch_anchors = {
        needle: [
            index
            for index, line in enumerate(h200_patch.splitlines(), 1)
            if needle in line
        ]
        for needle in (
            "self.draft_token_num = depth",
            "self.ngram_corpus.batch_get(",
            "[:, :depth]",
            "adaptive_graph_can_run",
        )
    }

    sources = {
        "ngram_corpus": SOURCE_ROOT / "speculative/cpp_ngram/ngram_corpus.py",
        "ngram_worker": SOURCE_ROOT / "speculative/ngram_worker.py",
        "ngram_info": SOURCE_ROOT / "speculative/ngram_info.py",
        "triton_backend": SOURCE_ROOT / "layers/attention/triton_backend.py",
        "decode_cuda_graph_runner": SOURCE_ROOT
        / "model_executor/runner/decode_cuda_graph_runner.py",
        "spec_utils": SOURCE_ROOT / "speculative/spec_utils.py",
        "batch_result_processor": SOURCE_ROOT
        / "managers/scheduler_components/batch_result_processor.py",
    }
    anchors = {
        "ngram_corpus": (
            "draft_token_num=draft_token_num",
            "self.draft_token_num = draft_token_num",
            "return self._obj.match_stateful",
        ),
        "ngram_worker": (
            "self.draft_token_num: int =",
            "draft_token_num=server_args.speculative_num_draft_tokens",
            "total_draft_token_num == bs * self.draft_token_num",
            "reconstruct_indices_from_tree_mask(",
            "end_offset=batch.seq_lens + self.draft_token_num",
            "draft_token_num=self.draft_token_num",
            ") = eagle_sample(",
            "move_accept_tokens_to_target_kvcache(",
            "speculative_num_draft_tokens=self.speculative_num_draft_tokens",
        ),
        "ngram_info": (
            "paged_kernel_lens = paged_kernel_lens + self.draft_token_num",
            "* self.draft_token_num",
            "self.accept_tokens.reshape(-1, self.draft_token_num)",
        ),
        "triton_backend": (
            "self.num_draft_tokens = model_runner.server_args.speculative_num_draft_tokens",
            "(1 + bs) * self.num_draft_tokens",
            "seq_mask_len = self.num_draft_tokens *",
            "max_extend_len = self.num_draft_tokens",
        ),
        "decode_cuda_graph_runner": (
            "self.num_tokens_per_bs = model_runner.decode_num_tokens_per_bs(",
            "forward_batch.batch_size * self.num_tokens_per_bs",
            "== forward_batch.input_ids.numel()",
            "raw_num_token = raw_bs * self.num_tokens_per_bs",
        ),
        "spec_utils": (
            "size = bs * accept_index.shape[1]",
            "batch.seq_lens + num_correct_drafts + 1",
            "move_kv_cache(",
        ),
        "batch_result_processor": (
            "stride = result.speculative_num_draft_tokens",
            "next_token_ids[i * stride : i * stride + accept_lens[i]]",
        ),
    }
    source_trace = {
        name: {
            "path": str(path),
            "sha256": sha256(path),
            "anchors": lines_with(path, anchors[name]),
        }
        for name, path in sources.items()
    }

    reconstruction = {
        "schema_version": 1,
        "classification": "prior_partial_representation_rejected",
        "evidence_label": "measured_h200_component_plus_source_backtrace",
        "compact": {
            "path": str(compact_path),
            "sha256": sha256(compact_path),
            "members": {
                name: {
                    "sha256": item["sha256"],
                    "bytes": item["bytes"],
                }
                for name, item in compact_members.items()
            },
        },
        "measured": {
            "reference": {
                "batch_size": component["reference"]["batch_size"],
                "draft_depth": component["reference"]["draft_depth"],
                "target_rows": component["reference"]["target_rows"],
            },
            "candidate": {
                "batch_size": component["candidate"]["batch_size"],
                "draft_depth": component["candidate"]["draft_depth"],
                "target_rows": component["candidate"]["target_rows"],
            },
            "exact_comparisons": {
                field: sum(bool(row[field]) for row in comparisons)
                for field in (
                    "draft_prefix_exact",
                    "target_predict_prefix_exact",
                    "num_correct_drafts_exact",
                    "accepted_bonus_tokens_exact",
                )
            },
            "comparison_requests": len(comparisons),
            "component_science_consumed": component["component_science_consumed"],
            "candidate_endpoint_science_consumed": final_terminal[
                "candidate_science_consumed"
            ],
            "terminal": final_terminal["result"],
        },
        "patch_anchors": patch_anchors,
        "first_violated_invariant": {
            "stage": "native_producer_to_worker_depth_ownership",
            "explanation": (
                "The compact patch mutated NGRAMWorker.draft_token_num to six while "
                "NgramCorpus remained a native fixed-depth-12 producer, then sliced "
                "the producer's tokens and mask. Production and consumption no "
                "longer had one depth owner even though the adapter returned "
                "six-row arrays."
            ),
            "not_hardware_effect": True,
        },
        "exact_v0515_repeat_defects": {
            "attention_metadata": (
                "Pinned v0.5.15 eager Triton target verify builds qo_indptr, "
                "per-request mask lengths, and max_extend_len from startup "
                "self.num_draft_tokens=12. Repeating the partial patch would "
                "describe 48 query rows as 96 before acceptance or KV movement."
            ),
            "scheduler_settlement": (
                "Pinned v0.5.15 NGRAMWorker returns "
                "speculative_num_draft_tokens from the immutable startup field "
                "(12), while a partial candidate packs next_token_ids at width 6; "
                "the scheduler uses that result field as its per-request stride."
            ),
            "evidence_scope": (
                "These two defects are source-backed for the bound H100 v0.5.15 "
                "snapshot. They are closure requirements for the new candidate, "
                "not claims that the uncaptured H200 attention source was identical."
            ),
        },
        "later_ownership_violation": {
            "stage": "exact_v0515_scheduler_settlement_if_partial_patch_repeated",
            "explanation": (
                "The worker returned speculative_num_draft_tokens from the immutable "
                "startup field (12), while candidate next_token_ids were packed at "
                "the active width (6); the scheduler uses that result field as its "
                "per-request slicing stride."
            ),
        },
        "source_trace": source_trace,
    }
    atomic_json(ROOT / "H200_FAILURE_RECONSTRUCTION.json", reconstruction)
    atomic_json(
        ROOT / "SOURCE_CONTRACT_TRACE.json",
        {
            "schema_version": 1,
            "result": "exact_v0515_contract_traced",
            "evidence_label": "source_backed",
            "source_trace": source_trace,
            "chain": [
                "NgramCorpus.__init__ fixes producer depth in the native object",
                "NgramCorpus.batch_get calls native match_stateful",
                "NGRAMWorker._prepare_draft_tokens requires bs*active_depth rows",
                "NGRAMWorker._prepare_for_speculative_decoding packs rows, positions, masks, and out_cache_loc",
                "TritonAttnBackend target-verify metadata currently uses startup depth",
                "eagle_sample consumes active NgramVerifyInput and target logits",
                "move_accept_tokens_to_target_kvcache derives width from accept_index",
                "GenerationBatchResult carries the scheduler slicing stride",
                "DecodeCudaGraphRunner admits only rows matching captured num_tokens_per_bs",
            ],
        },
    )
    print(json.dumps({"binding": binding_result, "reconstruction": reconstruction}, indent=2))


if __name__ == "__main__":
    main()
