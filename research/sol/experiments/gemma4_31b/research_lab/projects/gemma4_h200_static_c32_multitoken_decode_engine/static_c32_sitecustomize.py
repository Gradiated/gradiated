from __future__ import annotations

import hashlib
import importlib
import json
import os
import pathlib
import time


ARM = os.environ.get("STATIC_C32_ARM", "control")
AUDIT_PATH = pathlib.Path(
    os.environ.get("STATIC_C32_AUDIT", "/tmp/static-c32-audit.jsonl")
)
SUMMARY_PATH = pathlib.Path(
    os.environ.get("STATIC_C32_SUMMARY", "/tmp/static-c32-summary.json")
)
EXPECTED_CONCURRENCY = 32
TARGET_TOKENS = int(os.environ.get("STATIC_C32_TARGET", "358"))
COMMON_TOKENS = 535
INDEX_TOKEN_BASE = 200000
TOKENS: dict[int, list[int]] = {}
START_POSITIONS: dict[int, int] = {}
BLOCK_LENGTHS: list[int] = []
KV_TRANSITIONS: list[dict[str, object]] = []
START_MONOTONIC: float | None = None
DECODE_BOUNDARIES = 0
GRAPH_REPLAYS = 0
HOST_RESULT_SYNCS = 0
FINITE = True


def append(event: str, **fields: object) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "event": event,
                    "monotonic_s": time.monotonic(),
                    "pid": os.getpid(),
                    **fields,
                },
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def request_index(req) -> int:
    token = int(req.origin_input_ids[COMMON_TOKENS])
    index = token - INDEX_TOKEN_BASE
    if not 0 <= index < EXPECTED_CONCURRENCY:
        raise RuntimeError(f"static c32 request identity mismatch: {token}")
    return index


def exact_batch(batch) -> bool:
    if batch is None or len(batch.reqs) != EXPECTED_CONCURRENCY:
        return False
    try:
        indices = sorted(request_index(req) for req in batch.reqs)
    except (IndexError, RuntimeError):
        return False
    if indices != list(range(EXPECTED_CONCURRENCY)):
        return False
    return all(
        req.sampling_params.top_k == 1
        and req.sampling_params.ignore_eos
        and req.sampling_params.max_new_tokens
        == req.sampling_params.min_new_tokens
        for req in batch.reqs
    )


def target_block_len(batch) -> int:
    output_lengths = {len(req.output_ids) for req in batch.reqs}
    maxima = {req.sampling_params.max_new_tokens for req in batch.reqs}
    if len(output_lengths) != 1 or len(maxima) != 1:
        return 0
    output_len = output_lengths.pop()
    maximum = min(maxima.pop(), TARGET_TOKENS)
    remaining = maximum - output_len
    if remaining <= 0:
        return 0
    if output_len == 1:
        return min(7, remaining)
    return min(8, remaining)


def install_frontier() -> None:
    from install_endpoint_patch import EXPECTED_SHA256, NEW, OLD

    target = pathlib.Path(
        "/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py"
    )
    raw = target.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual == EXPECTED_SHA256:
        text = raw.decode()
        if text.count(OLD) != 1:
            raise RuntimeError("bound QKV patch target is not unique")
        target.write_text(text.replace(OLD, NEW))
    elif "qkv_norm_rope_inplace" not in raw.decode():
        raise RuntimeError(f"bound QKV source mismatch:{actual}")

    audit = os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
    if audit:
        os.environ["SYNC_CANDIDATE_AUDIT"] = audit
    attention = importlib.import_module("attention_deferred_local_kv")
    if "deferred_local_fp8_kv" not in attention.TARGET.read_text():
        attention.install()
    pinned = importlib.import_module("pinned_async_penalty_tokens")
    schedule_hash = hashlib.sha256(pinned.TARGET.read_bytes()).hexdigest()
    if schedule_hash == pinned.EXPECTED_SHA256:
        pinned.install()
    elif (
        schedule_hash
        != "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459"
    ):
        raise RuntimeError(f"pinned schedule_batch source mismatch:{schedule_hash}")
    importlib.import_module("host_min_new_tokens_gate").install()
    importlib.import_module("producer_fused_swa_translation").install()
    importlib.import_module("endpoint_ring_patch").install()


def write_summary(batch) -> None:
    expected = TARGET_TOKENS
    if len(TOKENS) != EXPECTED_CONCURRENCY:
        return
    if any(len(row) != expected for row in TOKENS.values()):
        return
    rows = [
        {
            "index": index,
            "start_position": START_POSITIONS[index],
            "token_ids": TOKENS[index],
            "token_count": len(TOKENS[index]),
        }
        for index in range(EXPECTED_CONCURRENCY)
    ]
    end_positions = {
        request_index(req): len(req.origin_input_ids) + len(req.output_ids) - 1
        for req in batch.reqs
    }
    elapsed = None if START_MONOTONIC is None else time.monotonic() - START_MONOTONIC
    summary = {
        "schema_version": 1,
        "arm": ARM,
        "pass": (
            FINITE
            and sorted(TOKENS) == list(range(EXPECTED_CONCURRENCY))
            and all(len(row["token_ids"]) == expected for row in rows)
        ),
        "concurrency": EXPECTED_CONCURRENCY,
        "completion_tokens": expected,
        "rows": rows,
        "block_lengths": BLOCK_LENGTHS,
        "decode_boundaries": DECODE_BOUNDARIES,
        "host_result_syncs": HOST_RESULT_SYNCS,
        "model_graph_replays": GRAPH_REPLAYS,
        "elapsed_decode_wall_seconds": elapsed,
        "finite_outputs": FINITE,
        "start_positions": START_POSITIONS,
        "end_positions": end_positions,
        "kv_transitions": KV_TRANSITIONS,
    }
    atomic_json(SUMMARY_PATH, summary)
    append("summary_written", pass_value=summary["pass"], rows=len(rows))


def install_static_executor() -> None:
    import torch
    from sglang.srt.managers.schedule_batch import ScheduleBatch
    from sglang.srt.managers.scheduler_components.batch_result_processor import (
        SchedulerBatchResultProcessor,
    )
    from sglang.srt.managers.tp_worker import TpModelWorker
    from sglang.srt.managers.utils import GenerationBatchResult
    from sglang.srt.mem_cache.common import alloc_token_slots
    from sglang.srt.model_executor.forward_batch_info import ForwardBatch

    original_prepare = ScheduleBatch.prepare_for_decode
    original_forward = TpModelWorker.forward_batch_generation
    original_copy = GenerationBatchResult.copy_to_cpu
    original_process = SchedulerBatchResultProcessor.process_batch_result_decode

    def prepare_for_decode(self):
        global START_MONOTONIC
        original_prepare(self)
        if self.reqs:
            try:
                workload_indices = sorted(request_index(req) for req in self.reqs)
            except (IndexError, RuntimeError):
                workload_indices = []
            if workload_indices:
                append(
                    "workload_decode_batch",
                    batch_size=len(self.reqs),
                    first_index=workload_indices[0],
                    last_index=workload_indices[-1],
                    output_lengths=sorted(
                        {len(req.output_ids) for req in self.reqs}
                    ),
                )
        if not exact_batch(self):
            return
        block_len = target_block_len(self)
        if block_len <= 0:
            return
        if START_MONOTONIC is None:
            START_MONOTONIC = time.monotonic()
        self._static_c32_block_len = block_len
        if ARM != "candidate":
            return

        bs = len(self.reqs)
        locations = [self.out_cache_loc]
        if block_len > 1:
            extra = alloc_token_slots(self.tree_cache, bs * (block_len - 1))
            if extra is None or extra.numel() != bs * (block_len - 1):
                raise RuntimeError("static c32 KV reservation failed")
            extra = extra.reshape(block_len - 1, bs)
            for offset in range(block_len - 1):
                columns = self.seq_lens + offset
                self.req_to_token_pool.write(
                    (self.req_pool_indices, columns),
                    extra[offset].to(torch.int32),
                )
                locations.append(extra[offset])
            for req in self.reqs:
                req.kv_allocated_len += block_len - 1
                req.kv_committed_len += block_len - 1
        self._static_c32_locations = torch.stack(locations)

    def forward_batch_generation(
        self,
        batch,
        forward_batch=None,
        pp_proxy_tensors=None,
        is_verify=False,
        skip_attn_backend_init=None,
        **kwargs,
    ):
        if (
            ARM != "candidate"
            or batch is None
            or not hasattr(batch, "_static_c32_locations")
        ):
            return original_forward(
                self,
                batch,
                forward_batch=forward_batch,
                pp_proxy_tensors=pp_proxy_tensors,
                is_verify=is_verify,
                skip_attn_backend_init=skip_attn_backend_init,
                **kwargs,
            )

        self.set_hicache_consumer(batch.hicache_consumer_index)
        fb = ForwardBatch.init_new(batch, self.model_runner)
        fb.apply_deprecated_skip_attn_backend_init(skip_attn_backend_init)
        first = self.model_runner.forward(fb, pp_proxy_tensors=pp_proxy_tensors)
        if not first.can_run_graph:
            raise RuntimeError("static c32 first forward missed CUDA graph")
        tokens = [self.model_runner.sample(first.logits_output, fb)]
        finite = [torch.isfinite(first.logits_output.next_token_logits).all()]
        runner = self.model_runner.graph_runner
        if runner is None or runner.bs != EXPECTED_CONCURRENCY:
            raise RuntimeError("static c32 graph runner identity mismatch")

        for step in range(1, int(batch._static_c32_block_len)):
            runner.buffers.input_ids[:EXPECTED_CONCURRENCY].copy_(tokens[-1])
            runner.buffers.positions[:EXPECTED_CONCURRENCY].add_(1)
            runner.buffers.seq_lens[:EXPECTED_CONCURRENCY].add_(1)
            runner.buffers.out_cache_loc[:EXPECTED_CONCURRENCY].copy_(
                batch._static_c32_locations[step]
            )
            runner.graphs[EXPECTED_CONCURRENCY].replay()
            shared_output = runner.output_buffers[EXPECTED_CONCURRENCY]
            finite.append(torch.isfinite(shared_output.next_token_logits).all())
            tokens.append(self.model_runner.sample(shared_output, fb))

        token_matrix = torch.stack(tokens, dim=1)
        result = GenerationBatchResult(
            logits_output=runner.output_buffers[EXPECTED_CONCURRENCY],
            next_token_ids=token_matrix[:, -1],
            can_run_cuda_graph=True,
        )
        result.static_c32_token_ids = token_matrix
        result.static_c32_finite = torch.stack(finite).all()
        result.static_c32_block_len = int(batch._static_c32_block_len)
        result.static_c32_locations = batch._static_c32_locations
        return result

    def copy_to_cpu(self, return_logprob, return_hidden_states=True):
        if hasattr(self, "static_c32_token_ids"):
            self.static_c32_token_ids = self.static_c32_token_ids.to(
                "cpu", non_blocking=True
            )
            self.static_c32_finite = self.static_c32_finite.to(
                "cpu", non_blocking=True
            )
            self.static_c32_locations = self.static_c32_locations.to(
                "cpu", non_blocking=True
            )
        return original_copy(self, return_logprob, return_hidden_states)

    def process_batch_result_decode(self, batch, result):
        global DECODE_BOUNDARIES, FINITE, GRAPH_REPLAYS, HOST_RESULT_SYNCS
        if SUMMARY_PATH.exists() or not exact_batch(batch):
            return original_process(self, batch, result)

        if result.copy_done is not None:
            result.copy_done.synchronize()
        DECODE_BOUNDARIES += 1
        HOST_RESULT_SYNCS += 1

        first_boundary = not TOKENS
        if first_boundary:
            positions = batch.seq_lens.tolist()
            for row, req in enumerate(batch.reqs):
                index = request_index(req)
                TOKENS[index] = [int(req.output_ids[-1])]
                START_POSITIONS[index] = int(positions[row] - 1)

        if not hasattr(result, "static_c32_token_ids"):
            original_process(self, batch, result)
            GRAPH_REPLAYS += 1
            BLOCK_LENGTHS.append(1)
            for req in batch.reqs:
                TOKENS[request_index(req)].append(int(req.output_ids[-1]))
            append(
                "control_decode_boundary",
                token_counts=sorted({len(values) for values in TOKENS.values()}),
            )
            write_summary(batch)
            return

        token_matrix = result.static_c32_token_ids.tolist()
        locations = result.static_c32_locations.tolist()
        finite = bool(result.static_c32_finite.item())
        block_len = int(result.static_c32_block_len)
        FINITE = FINITE and finite
        GRAPH_REPLAYS += block_len
        BLOCK_LENGTHS.append(block_len)

        self.metrics_reporter.num_generated_tokens += len(batch.reqs) * block_len
        if self.server_args.enable_metrics:
            self.metrics_collector.increment_decode_cuda_graph_pass(value=True)
        self.token_to_kv_pool_allocator.free_group_begin()
        for row, req in enumerate(batch.reqs):
            values = [int(token) for token in token_matrix[row]]
            req.output_ids.extend(values)
            TOKENS[request_index(req)].extend(values)
            self._maybe_update_reasoning_tokens(req, values)
            req.time_stats.set_last_decode_finish_time()
            req.update_finish_state(block_len)
            self._handle_finish_state_updated_req(
                req, batch, result, row, result.logits_output
            )
        self.output_streamer.stream_output(batch.reqs, batch.return_logprob)
        self.token_to_kv_pool_allocator.free_group_end()
        self.metrics_reporter.forward_ct_decode = (
            self.metrics_reporter.forward_ct_decode + 1
        ) % (1 << 30)
        self.metrics_reporter.report_decode_stats(
            True, running_batch=batch, num_correct_drafts=0
        )

        if block_len > 1:
            batch.seq_lens.add_(block_len - 1)
            batch.seq_lens_cpu.add_(block_len - 1)
            batch.orig_seq_lens.add_(block_len - 1)
            batch.seq_lens_sum = None
        transition = {
            "block_len": block_len,
            "location_rows": len(locations),
            "location_width": len(locations[0]) if locations else 0,
            "locations_unique": len({value for row in locations for value in row})
            == block_len * EXPECTED_CONCURRENCY,
            "output_lengths": sorted({len(req.output_ids) for req in batch.reqs}),
            "kv_allocated_lengths": sorted(
                {int(req.kv_allocated_len) for req in batch.reqs}
            ),
            "kv_committed_lengths": sorted(
                {int(req.kv_committed_len) for req in batch.reqs}
            ),
            "seq_lens": sorted({int(value) for value in batch.seq_lens_cpu.tolist()}),
        }
        KV_TRANSITIONS.append(transition)
        append("candidate_decode_block", finite=finite, **transition)
        write_summary(batch)

    ScheduleBatch.prepare_for_decode = prepare_for_decode
    TpModelWorker.forward_batch_generation = forward_batch_generation
    GenerationBatchResult.copy_to_cpu = copy_to_cpu
    SchedulerBatchResultProcessor.process_batch_result_decode = (
        process_batch_result_decode
    )
    append("static_c32_installed", arm=ARM)


install_frontier()
install_static_executor()
