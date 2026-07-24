from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import torch


TREE_DEPTH = 12
STAGE_DEPTH = 6
HIGH_LOAD_MIN_REQUESTS = 8
OUT = Path(os.environ.get("TWO_STAGE_OUT", "/work/out"))
EVENT_LOCK = threading.Lock()


def append_event(value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    with EVENT_LOCK:
        descriptor = os.open(
            OUT / "TWO_STAGE_EVENTS.jsonl",
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o644,
        )
        try:
            os.write(descriptor, raw)
        finally:
            os.close(descriptor)


def atomic_once(name: str, value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    if path.exists():
        return
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def tensor_sha256(value: torch.Tensor) -> str:
    return hashlib.sha256(
        value.detach().contiguous().cpu().numpy().tobytes()
    ).hexdigest()


def split_rows(value: torch.Tensor, batch_size: int, begin: int, end: int):
    return value.reshape(batch_size, TREE_DEPTH, *value.shape[1:])[
        :, begin:end
    ].reshape(batch_size * (end - begin), *value.shape[1:])


def split_matrix(value: torch.Tensor, begin: int, end: int):
    return value[:, begin:end]


def timed_forward(worker, batch, is_verify: bool):
    started = torch.cuda.Event(enable_timing=True)
    ended = torch.cuda.Event(enable_timing=True)
    started.record()
    wall_started = time.perf_counter()
    result = worker.forward_batch_generation(batch, is_verify=is_verify)
    ended.record()
    ended.synchronize()
    return result, started.elapsed_time(ended), time.perf_counter() - wall_started


def set_backend_depth(forward_batch, backend, original):
    spec_info = getattr(forward_batch, "spec_info", None)
    if (
        forward_batch.forward_mode.is_target_verify()
        and spec_info is not None
    ):
        prior = backend.num_draft_tokens
        backend.num_draft_tokens = spec_info.draft_token_num
        try:
            return original(backend, forward_batch)
        finally:
            backend.num_draft_tokens = prior
    return original(backend, forward_batch)


def apply_probe_processors(batch, logits: torch.Tensor) -> None:
    sampling_info = batch.sampling_info
    if sampling_info.has_custom_logit_processor:
        raise RuntimeError("two_stage_custom_logit_processor_unsupported")
    if batch.has_grammar:
        raise RuntimeError("two_stage_grammar_unsupported")
    if (
        sampling_info.penalizer_orchestrator.is_required
        or sampling_info.logit_bias is not None
    ):
        sampling_info.penalizer_orchestrator.apply(
            logits, repeat=STAGE_DEPTH
        )
        if sampling_info.logit_bias is not None:
            logits.add_(
                torch.repeat_interleave(
                    sampling_info.logit_bias, STAGE_DEPTH, dim=0
                )
            )


def survivor_indices(full_spec, batch, stage_one_logits: torch.Tensor):
    from sgl_kernel import verify_tree_greedy

    batch_size = batch.batch_size()
    processed = stage_one_logits.clone()
    apply_probe_processors(batch, processed)
    first_predict = torch.argmax(processed, dim=-1).reshape(
        batch_size, STAGE_DEPTH
    )
    target_predict = torch.full(
        (batch_size, TREE_DEPTH),
        -1,
        dtype=first_predict.dtype,
        device=first_predict.device,
    )
    target_predict[:, :STAGE_DEPTH] = first_predict
    predicts = torch.empty(
        (batch_size * TREE_DEPTH + 1,),
        dtype=torch.int32,
        device=first_predict.device,
    )
    accept_indices = torch.full(
        (batch_size, TREE_DEPTH),
        -1,
        dtype=torch.int32,
        device=first_predict.device,
    )
    accepted_drafts = torch.empty(
        (batch_size,), dtype=torch.int32, device=first_predict.device
    )
    verify_tree_greedy(
        predicts=predicts,
        accept_index=accept_indices,
        accept_token_num=accepted_drafts,
        candidates=full_spec.draft_token.reshape(batch_size, TREE_DEPTH),
        retrive_index=full_spec.retrieve_index,
        retrive_next_token=full_spec.retrieve_next_token,
        retrive_next_sibling=full_spec.retrieve_next_sibling,
        target_predict=target_predict,
    )
    accepted = accepted_drafts.cpu().tolist()
    survivors = [
        index
        for index, count in enumerate(accepted)
        if count >= STAGE_DEPTH
    ]
    return survivors, accepted, first_predict


def split_custom_mask(
    full_spec,
    seq_lens_cpu: torch.Tensor,
    begin: int,
    end: int,
    request_indices: list[int] | None = None,
) -> tuple[torch.Tensor, bool]:
    batch_size = len(seq_lens_cpu)
    selected = (
        list(range(batch_size))
        if request_indices is None
        else request_indices
    )
    full_mask = full_spec.custom_mask
    if full_mask.numel() == batch_size * TREE_DEPTH * TREE_DEPTH:
        matrix = full_mask.reshape(batch_size, TREE_DEPTH, TREE_DEPTH)
        cropped = matrix[selected, begin:end, begin:end]
        return cropped.contiguous().reshape(-1), True

    widths = [int(value) + TREE_DEPTH for value in seq_lens_cpu.tolist()]
    expected = sum(TREE_DEPTH * width for width in widths)
    if full_mask.numel() != expected:
        raise RuntimeError(
            "two_stage_custom_mask_shape_mismatch:"
            f"{full_mask.numel()}:{expected}"
        )
    selected_set = set(selected)
    pieces = []
    offset = 0
    for index, width in enumerate(widths):
        count = TREE_DEPTH * width
        if index in selected_set:
            matrix = full_mask[offset : offset + count].reshape(
                TREE_DEPTH, width
            )
            prefix = width - TREE_DEPTH
            pieces.append(
                matrix[begin:end, : prefix + end].contiguous().reshape(-1)
            )
        offset += count
    return torch.cat(pieces), False


def make_stage_spec(
    full_spec,
    seq_lens_cpu: torch.Tensor,
    begin: int,
    end: int,
    request_indices: list[int] | None = None,
):
    from sglang.srt.speculative.ngram_info import NgramVerifyInput

    batch_size = len(seq_lens_cpu)
    depth = end - begin
    selected = (
        list(range(batch_size))
        if request_indices is None
        else request_indices
    )
    selected_tensor = torch.tensor(
        selected, dtype=torch.int64, device=full_spec.draft_token.device
    )
    custom_mask, compact_mask = split_custom_mask(
        full_spec,
        seq_lens_cpu,
        begin,
        end,
        selected,
    )
    draft_token = split_rows(
        full_spec.draft_token, batch_size, begin, end
    ).reshape(batch_size, depth)[selected_tensor].reshape(-1)
    positions = split_rows(
        full_spec.positions, batch_size, begin, end
    ).reshape(batch_size, depth)[selected_tensor].reshape(-1)
    return NgramVerifyInput(
        draft_token,
        custom_mask,
        positions,
        split_matrix(full_spec.retrieve_index, begin, end)[selected_tensor],
        split_matrix(full_spec.retrieve_next_token, begin, end)[
            selected_tensor
        ],
        split_matrix(full_spec.retrieve_next_sibling, begin, end)[
            selected_tensor
        ],
        depth,
    ), compact_mask


def install() -> None:
    from sglang.srt.layers.attention.triton_backend import TritonAttnBackend
    from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner
    from sglang.srt.model_executor.forward_batch_info import ForwardMode
    from sglang.srt.observability.req_time_stats import set_time_batch
    from sglang.srt.observability.trace import get_global_tracing_enabled
    from sglang.srt.speculative.ngram_worker import NGRAMWorker
    from sglang.srt.managers.scheduler import GenerationBatchResult

    original_forward = NGRAMWorker.forward_batch_generation
    original_can_run = CudaGraphRunner.can_run
    original_metadata = TritonAttnBackend.init_forward_metadata

    def can_run(graph_runner, forward_batch) -> bool:
        if (
            forward_batch.forward_mode.is_target_verify()
            and forward_batch.batch_size >= HIGH_LOAD_MIN_REQUESTS
        ):
            return False
        return original_can_run(graph_runner, forward_batch)

    def metadata(backend, forward_batch):
        return set_backend_depth(forward_batch, backend, original_metadata)

    def two_stage_forward(self: NGRAMWorker, batch):
        if (
            batch.forward_mode.is_extend()
            or batch.batch_size() < HIGH_LOAD_MIN_REQUESTS
        ):
            return original_forward(self, batch)
        if self.draft_token_num != TREE_DEPTH:
            raise RuntimeError(
                f"two_stage_requires_depth_12:{self.draft_token_num}"
            )
        if batch.return_logprob or batch.has_grammar:
            raise RuntimeError("two_stage_bound_workload_contract_violation")

        set_time_batch(batch.reqs, "set_spec_draft_start_time", trace_only=True)
        self._prepare_for_speculative_decoding(batch)
        set_time_batch(batch.reqs, "set_spec_draft_end_time", trace_only=True)

        if not batch.forward_mode.is_target_verify():
            return original_forward(self, batch)

        set_time_batch(batch.reqs, "set_spec_verify_start_time", trace_only=True)
        full_spec = batch.spec_info
        batch_size = batch.batch_size()
        full_input_ids = batch.input_ids
        full_out_cache_loc = batch.out_cache_loc
        full_slots = full_out_cache_loc.reshape(batch_size, TREE_DEPTH)
        stage_one_spec, compact_mask = make_stage_spec(
            full_spec, batch.seq_lens_cpu, 0, STAGE_DEPTH
        )
        batch.spec_info = stage_one_spec
        batch.input_ids = split_rows(
            full_input_ids, batch_size, 0, STAGE_DEPTH
        )
        batch.out_cache_loc = full_slots[:, :STAGE_DEPTH].contiguous().reshape(-1)

        stage_one_result, stage_one_ms, stage_one_wall = timed_forward(
            self.target_worker, batch, True
        )
        stage_one_logits = stage_one_result.logits_output.next_token_logits
        survivors, probe_accepted, first_predict = survivor_indices(
            full_spec, batch, stage_one_logits
        )

        combined_shape = (
            batch_size,
            TREE_DEPTH,
            stage_one_logits.shape[-1],
        )
        combined_logits = torch.zeros(
            combined_shape,
            dtype=stage_one_logits.dtype,
            device=stage_one_logits.device,
        )
        combined_logits[:, :STAGE_DEPTH] = stage_one_logits.reshape(
            batch_size, STAGE_DEPTH, -1
        )
        stage_two_ms = 0.0
        stage_two_wall = 0.0
        continuation_prefix_mask_all_true = True

        if survivors:
            survivor_tensor = torch.tensor(
                survivors, dtype=torch.int64, device=full_input_ids.device
            )
            if compact_mask:
                full_mask = full_spec.custom_mask.reshape(
                    batch_size, TREE_DEPTH, TREE_DEPTH
                )
                continuation_prefix_mask_all_true = bool(
                    full_mask[
                        survivor_tensor, STAGE_DEPTH:, :STAGE_DEPTH
                    ]
                    .all()
                    .item()
                )
                if not continuation_prefix_mask_all_true:
                    raise RuntimeError(
                        "two_stage_non_linear_continuation_prefix_mask"
                    )
            continuation_batch = copy.copy(batch)
            continuation_batch.sampling_info = copy.deepcopy(
                batch.sampling_info
            )
            continuation_batch.spec_info = None
            continuation_batch.filter_batch(keep_indices=survivors)
            continuation_batch.seq_lens = (
                continuation_batch.seq_lens + STAGE_DEPTH
            )
            continuation_batch.seq_lens_cpu = (
                continuation_batch.seq_lens_cpu + STAGE_DEPTH
            )
            continuation_batch.seq_lens_sum = int(
                continuation_batch.seq_lens_cpu.sum().item()
            )
            continuation_spec, continuation_compact = make_stage_spec(
                full_spec,
                batch.seq_lens_cpu,
                STAGE_DEPTH,
                TREE_DEPTH,
                survivors,
            )
            if continuation_compact != compact_mask:
                raise RuntimeError("two_stage_mask_representation_changed")
            continuation_batch.spec_info = continuation_spec
            continuation_batch.input_ids = continuation_spec.draft_token
            continuation_batch.out_cache_loc = full_slots[
                survivor_tensor, STAGE_DEPTH:
            ].contiguous().reshape(-1)
            continuation_batch.forward_mode = ForwardMode.TARGET_VERIFY
            stage_two_result, stage_two_ms, stage_two_wall = timed_forward(
                self.target_worker, continuation_batch, True
            )
            combined_logits[survivor_tensor, STAGE_DEPTH:] = (
                stage_two_result.logits_output.next_token_logits.reshape(
                    len(survivors), STAGE_DEPTH, -1
                )
            )

        batch.spec_info = full_spec
        batch.input_ids = full_input_ids
        batch.out_cache_loc = full_out_cache_loc
        logits_output = copy.copy(stage_one_result.logits_output)
        logits_output.next_token_logits = combined_logits.reshape(
            batch_size * TREE_DEPTH, -1
        )
        logits_output, next_token_ids, num_correct_drafts = full_spec.verify(
            batch, logits_output, self.page_size, None
        )
        num_correct_per_request = full_spec.num_correct_drafts.cpu().tolist()
        accept_counts = full_spec.num_accept_tokens.cpu().tolist()
        accepted_bonus_tokens = []
        cursor = 0
        accept_tokens_cpu = full_spec.accept_tokens.cpu().tolist()
        for count in accept_counts:
            accepted_bonus_tokens.append(
                accept_tokens_cpu[cursor : cursor + count]
            )
            cursor += count

        if get_global_tracing_enabled():
            for index, request in enumerate(batch.reqs):
                request.time_stats.set_spec_verify_end_time(
                    num_correct_drafts=num_correct_per_request[index]
                )
        accept_lens = full_spec.num_accept_tokens
        self._update_ngram_corpus(batch)
        finished = [
            request.rid
            for request in batch.reqs
            if request.finished() or request.is_retracted
        ]
        if finished:
            self.ngram_corpus.erase_match_state(finished)
        batch.forward_mode = ForwardMode.DECODE

        request_ids = [
            hashlib.sha256(str(request.rid).encode()).hexdigest()
            for request in batch.reqs
        ]
        accepted_slots = batch.out_cache_loc
        append_event(
            {
                "schema_version": 1,
                "batch_size": batch_size,
                "request_ids_sha256": request_ids,
                "tree_depth": TREE_DEPTH,
                "producer_tree_unchanged": True,
                "draft_tokens_sha256": tensor_sha256(full_spec.draft_token),
                "tree_mask_sha256": tensor_sha256(full_spec.custom_mask),
                "stage_one_rows": batch_size * STAGE_DEPTH,
                "stage_one_target_forward_ms": stage_one_ms,
                "stage_one_target_forward_wall_seconds": stage_one_wall,
                "stage_one_target_predict": first_predict.cpu().tolist(),
                "probe_accepted_drafts_before_late_sentinel": probe_accepted,
                "stage_survivor_indices": survivors,
                "stage_survivor_count": len(survivors),
                "stage_two_rows": len(survivors) * STAGE_DEPTH,
                "stage_two_target_forward_ms": stage_two_ms,
                "stage_two_target_forward_wall_seconds": stage_two_wall,
                "continuation_prefix_mask_all_true": (
                    continuation_prefix_mask_all_true
                ),
                "target_rows": (
                    batch_size * STAGE_DEPTH
                    + len(survivors) * STAGE_DEPTH
                ),
                "full_target_rows": batch_size * TREE_DEPTH,
                "target_rows_saved": (
                    (batch_size - len(survivors)) * STAGE_DEPTH
                ),
                "full_cache_slots": int(full_slots.numel()),
                "full_cache_slots_unique": (
                    int(torch.unique(full_slots).numel())
                    == int(full_slots.numel())
                ),
                "stage_one_cache_slots": batch_size * STAGE_DEPTH,
                "stage_two_cache_slots_owned_by_survivors": (
                    len(survivors) * STAGE_DEPTH
                ),
                "accepted_cache_slots": int(accepted_slots.numel()),
                "accepted_cache_slots_unique": (
                    int(torch.unique(accepted_slots).numel())
                    == int(accepted_slots.numel())
                ),
                "num_correct_drafts": num_correct_per_request,
                "accepted_bonus_tokens": accepted_bonus_tokens,
            }
        )
        return GenerationBatchResult(
            logits_output=logits_output,
            next_token_ids=next_token_ids,
            num_correct_drafts=num_correct_drafts,
            num_correct_drafts_per_req_cpu=num_correct_per_request,
            can_run_cuda_graph=False,
            accept_lens=accept_lens,
        )

    CudaGraphRunner.can_run = can_run
    TritonAttnBackend.init_forward_metadata = metadata
    NGRAMWorker.forward_batch_generation = two_stage_forward
    atomic_once(
        "TWO_STAGE_PATCH_STATE.json",
        {
            "kind": "conditional_two_stage_target_verification",
            "tree_depth": TREE_DEPTH,
            "stage_one_rows": STAGE_DEPTH,
            "stage_two_rows": STAGE_DEPTH,
            "high_load_min_running_requests": HIGH_LOAD_MIN_REQUESTS,
            "producer": "unchanged NgramCorpus depth-12 tree",
            "consumer": "unchanged full-depth NgramVerifyInput.verify",
            "target_execution": (
                "six rows for all high-load requests, then six rows only "
                "for full-tree traversals reaching the continuation"
            ),
        },
    )


install()
