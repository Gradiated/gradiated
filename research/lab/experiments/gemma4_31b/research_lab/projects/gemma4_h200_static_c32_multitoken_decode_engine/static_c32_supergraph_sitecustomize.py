from __future__ import annotations

import hashlib
import importlib
import json
import os
import pathlib
import time
import copy


ARM = os.environ.get("STATIC_C32_ARM", "control")
AUDIT_PATH = pathlib.Path(
    os.environ.get("STATIC_C32_AUDIT", "/tmp/static-c32-supergraph-audit.jsonl")
)
SUMMARY_PATH = pathlib.Path(
    os.environ.get("STATIC_C32_SUMMARY", "/tmp/static-c32-supergraph-summary.json")
)
EXPECTED_CONCURRENCY = 32
TARGET_TOKENS = int(os.environ.get("STATIC_C32_TARGET", "358"))
COMMON_TOKENS = 535
INDEX_TOKEN_BASE = 200000
TOKENS: dict[int, list[int]] = {}
ORACLE_TOKENS: dict[int, list[int]] = {}
START_POSITIONS: dict[int, int] = {}
BLOCK_LENGTHS: list[int] = []
TRANSITIONS: list[dict[str, object]] = []
SUPERGRAPHS: dict[int, "FixedBlockSupergraph"] = {}
START_MONOTONIC: float | None = None
DECODE_BOUNDARIES = 0
GRAPH_REPLAYS = 0
HOST_RESULT_SYNCS = 0
FINITE = True
TOKEN_EXACT = True
POSITION_EXACT = True
KV_EXACT = True
REQUEST_MAP_EXACT = True
CANDIDATE_DEVICE_MS = 0.0


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
    return indices == list(range(EXPECTED_CONCURRENCY)) and all(
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
    remaining = min(maxima.pop(), TARGET_TOKENS) - output_len
    if remaining <= 0:
        return 0
    # The first completion token was produced by prefill, so the first
    # logical eight-token block contains seven decode forwards.
    return min(7 if output_len == 1 else 8, remaining)


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


def _selected_finite(torch, logits, tokens):
    chosen = logits.gather(1, tokens[:, None]).squeeze(1)
    return torch.isfinite(chosen).all() & ~torch.isnan(logits).any()


def _kv_locations(pool, layer_id: int, locations):
    mapping = getattr(pool, "layers_mapping", {}).get(layer_id)
    if mapping is not None and bool(mapping[1]):
        return pool.translate_loc_from_full_to_swa(locations)
    return locations


def _snapshot_kv(torch, pool, locations):
    snapshots = []
    layer_ids = sorted(getattr(pool, "layers_mapping", {}))
    if not layer_ids:
        layer_ids = list(range(int(pool.layer_num)))
    flat = locations.reshape(-1)
    for layer_id in layer_ids:
        loc = _kv_locations(pool, layer_id, flat)
        snapshots.append(
            (
                layer_id,
                loc,
                pool.get_key_buffer(layer_id).index_select(0, loc).clone(),
                pool.get_value_buffer(layer_id).index_select(0, loc).clone(),
            )
        )
    return snapshots


def _compare_kv_bytes(torch, pool, snapshots):
    exact = torch.ones((), dtype=torch.bool, device="cuda")
    compared = 0
    for layer_id, loc, expected_k, expected_v in snapshots:
        actual_k = pool.get_key_buffer(layer_id).index_select(0, loc)
        actual_v = pool.get_value_buffer(layer_id).index_select(0, loc)
        exact &= (actual_k.view(torch.uint8) == expected_k.view(torch.uint8)).all()
        exact &= (actual_v.view(torch.uint8) == expected_v.view(torch.uint8)).all()
        compared += actual_k.numel() * actual_k.element_size()
        compared += actual_v.numel() * actual_v.element_size()
    return exact, compared


class FixedBlockSupergraph:
    """One fixed-shape c32 graph containing every ordered decode dependency."""

    def __init__(
        self,
        torch,
        runner,
        template_fb,
        block_len: int,
        input_ids,
        positions,
        seq_lens,
        locations,
    ):
        from sglang.srt.model_executor.cuda_graph_runner import build_replay_fb_view

        self.torch = torch
        self.runner = runner
        self.block_len = block_len
        device = runner.buffers.input_ids.device
        self.input_ids = torch.empty(
            EXPECTED_CONCURRENCY, dtype=torch.int64, device=device
        )
        self.positions = torch.empty(
            (block_len, EXPECTED_CONCURRENCY), dtype=torch.int64, device=device
        )
        self.seq_lens = torch.empty(
            (block_len, EXPECTED_CONCURRENCY), dtype=torch.int32, device=device
        )
        self.locations = torch.empty(
            (block_len, EXPECTED_CONCURRENCY),
            dtype=runner.buffers.out_cache_loc.dtype,
            device=device,
        )
        self.tokens = torch.empty(
            (EXPECTED_CONCURRENCY, block_len), dtype=torch.int64, device=device
        )
        self.finite = torch.empty(block_len, dtype=torch.bool, device=device)
        self.graph = torch.cuda.CUDAGraph()
        self.load(input_ids, positions, seq_lens, locations)

        # Prepare graph-runner identity and stable metadata views before the first
        # candidate CUDA capture. All values are overwritten by load() below.
        runner.replay_prepare(template_fb)
        if runner.bs != EXPECTED_CONCURRENCY:
            raise RuntimeError(f"supergraph padded batch mismatch:{runner.bs}")
        fb_view = build_replay_fb_view(
            forward_batch=template_fb,
            buffers=runner.buffers,
            bs=EXPECTED_CONCURRENCY,
            raw_bs=EXPECTED_CONCURRENCY,
            num_tokens=EXPECTED_CONCURRENCY,
            seq_len_fill_value=runner.seq_len_fill_value,
            capture_forward_mode=runner.capture_forward_mode,
            is_encoder_decoder=runner.is_encoder_decoder,
        )
        # The stock helper retains the caller's original out_cache_loc object.
        # The supergraph explicitly binds the stable device buffer updated at
        # every dependent step.
        fb_view.out_cache_loc = runner.buffers.out_cache_loc[:EXPECTED_CONCURRENCY]
        output = runner.output_buffers[EXPECTED_CONCURRENCY]
        backend = runner.attn_backend

        torch.cuda.synchronize()
        append("supergraph_capture_started", block_len=block_len)
        with torch.cuda.graph(self.graph):
            for step in range(block_len):
                if step == 0:
                    runner.buffers.input_ids[:EXPECTED_CONCURRENCY].copy_(
                        self.input_ids
                    )
                else:
                    runner.buffers.input_ids[:EXPECTED_CONCURRENCY].copy_(
                        self.tokens[:, step - 1]
                    )
                runner.buffers.positions[:EXPECTED_CONCURRENCY].copy_(
                    self.positions[step]
                )
                runner.buffers.seq_lens[:EXPECTED_CONCURRENCY].copy_(
                    self.seq_lens[step]
                )
                runner.buffers.out_cache_loc[:EXPECTED_CONCURRENCY].copy_(
                    self.locations[step]
                )
                backend.init_forward_metadata_out_graph(fb_view)
                runner.graphs[EXPECTED_CONCURRENCY].replay()
                logits = output.next_token_logits[:EXPECTED_CONCURRENCY]
                token = torch.argmax(logits, dim=-1)
                self.tokens[:, step].copy_(token)
                self.finite[step].copy_(_selected_finite(torch, logits, token))
        torch.cuda.synchronize()
        append(
            "supergraph_capture_complete",
            block_len=block_len,
            child_forwards=block_len,
        )

    def load(self, input_ids, positions, seq_lens, locations) -> None:
        self.input_ids.copy_(input_ids)
        self.positions.copy_(positions)
        self.seq_lens.copy_(seq_lens)
        self.locations.copy_(locations)

    def replay(self):
        start = self.torch.cuda.Event(enable_timing=True)
        end = self.torch.cuda.Event(enable_timing=True)
        start.record()
        self.graph.replay()
        end.record()
        return start, end


def _oracle_block(torch, runner, template_fb, input_ids, positions, seq_lens, locations):
    tokens = torch.empty(
        (EXPECTED_CONCURRENCY, locations.shape[0]),
        dtype=torch.int64,
        device=input_ids.device,
    )
    finite = torch.ones((), dtype=torch.bool, device=input_ids.device)
    current = input_ids
    for step in range(locations.shape[0]):
        fb = copy.copy(template_fb)
        fb.input_ids = current
        fb.positions = positions[step]
        fb.seq_lens = seq_lens[step]
        fb.seq_lens_cpu = seq_lens[step].to("cpu")
        fb.out_cache_loc = locations[step]
        output = runner.replay(fb)
        logits = output.next_token_logits[:EXPECTED_CONCURRENCY]
        current = torch.argmax(logits, dim=-1)
        tokens[:, step].copy_(current)
        finite &= _selected_finite(torch, logits, current)
    # This is a semantic oracle, deliberately not a timing arm.
    torch.cuda.synchronize()
    return tokens, finite


def write_summary(batch) -> None:
    if len(TOKENS) != EXPECTED_CONCURRENCY:
        return
    if any(len(row) != TARGET_TOKENS for row in TOKENS.values()):
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
    oracle_rows = [
        {"index": index, "token_ids": ORACLE_TOKENS.get(index, [])}
        for index in range(EXPECTED_CONCURRENCY)
    ]
    end_positions = {
        request_index(req): len(req.origin_input_ids) + len(req.output_ids) - 1
        for req in batch.reqs
    }
    component = TARGET_TOKENS == 22 and ARM == "candidate"
    pass_value = (
        FINITE
        and (not component or TOKEN_EXACT)
        and (not component or POSITION_EXACT)
        and (not component or KV_EXACT)
        and (not component or REQUEST_MAP_EXACT)
        and all(len(row["token_ids"]) == TARGET_TOKENS for row in rows)
    )
    summary = {
        "schema_version": 2,
        "arm": ARM,
        "pass": pass_value,
        "concurrency": EXPECTED_CONCURRENCY,
        "completion_tokens": TARGET_TOKENS,
        "rows": rows,
        "oracle_rows": oracle_rows if component else [],
        "block_lengths": BLOCK_LENGTHS,
        "decode_boundaries": DECODE_BOUNDARIES,
        "host_result_syncs": HOST_RESULT_SYNCS,
        "control_host_boundaries": sum(BLOCK_LENGTHS) if component else None,
        "model_graph_replays": GRAPH_REPLAYS,
        "elapsed_decode_wall_seconds": (
            None if START_MONOTONIC is None else time.monotonic() - START_MONOTONIC
        ),
        "oracle_timed": False if component else None,
        "candidate_device_ms": CANDIDATE_DEVICE_MS if component else None,
        "finite_outputs": FINITE,
        "token_id_equality": TOKEN_EXACT if component else None,
        "position_transition_equality": POSITION_EXACT if component else None,
        "kv_byte_exact": KV_EXACT if component else None,
        "request_map_byte_exact": REQUEST_MAP_EXACT if component else None,
        "start_positions": START_POSITIONS,
        "end_positions": end_positions,
        "transitions": TRANSITIONS,
    }
    atomic_json(SUMMARY_PATH, summary)
    append("summary_written", pass_value=pass_value, rows=len(rows))


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
        if SUMMARY_PATH.exists():
            return
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
        locations = [self.out_cache_loc]
        if block_len > 1:
            extra = alloc_token_slots(
                self.tree_cache, EXPECTED_CONCURRENCY * (block_len - 1)
            )
            if extra is None or extra.numel() != EXPECTED_CONCURRENCY * (
                block_len - 1
            ):
                raise RuntimeError("supergraph KV reservation failed")
            extra = extra.reshape(block_len - 1, EXPECTED_CONCURRENCY)
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
        template_fb = ForwardBatch.init_new(batch, self.model_runner)
        template_fb.apply_deprecated_skip_attn_backend_init(skip_attn_backend_init)
        runner = self.model_runner.graph_runner
        if runner is None:
            raise RuntimeError("supergraph CUDA graph runner unavailable")
        block_len = int(batch._static_c32_block_len)
        locations = batch._static_c32_locations
        start_input = template_fb.input_ids.clone()
        start_positions = template_fb.positions.clone()
        start_seq_lens = template_fb.seq_lens.clone()
        positions = torch.stack(
            [start_positions + step for step in range(block_len)]
        )
        seq_lens = torch.stack(
            [start_seq_lens + step for step in range(block_len)]
        )

        component = TARGET_TOKENS == 22
        oracle_tokens = None
        oracle_finite = torch.ones((), dtype=torch.bool, device=start_input.device)
        snapshots = None
        if component:
            oracle_tokens, oracle_finite = _oracle_block(
                torch,
                runner,
                template_fb,
                start_input,
                positions,
                seq_lens,
                locations,
            )
            pool = self.model_runner.token_to_kv_pool
            snapshots = _snapshot_kv(torch, pool, locations)

        graph = SUPERGRAPHS.get(block_len)
        if graph is None:
            graph = FixedBlockSupergraph(
                torch,
                runner,
                template_fb,
                block_len,
                start_input,
                positions,
                seq_lens,
                locations,
            )
            SUPERGRAPHS[block_len] = graph
        else:
            graph.load(start_input, positions, seq_lens, locations)
        candidate_start, candidate_end = graph.replay()

        token_exact = torch.ones((), dtype=torch.bool, device=start_input.device)
        position_exact = (
            runner.buffers.positions[:EXPECTED_CONCURRENCY] == positions[-1]
        ).all()
        map_expected = locations.to(torch.int32)
        columns = start_seq_lens[None, :] + torch.arange(
            block_len, dtype=torch.int32, device=start_input.device
        )[:, None]
        map_actual = batch.req_to_token_pool.req_to_token[
            batch.req_pool_indices[None, :], columns
        ]
        map_exact = (map_actual == map_expected).all()
        kv_exact = torch.ones((), dtype=torch.bool, device=start_input.device)
        kv_bytes = 0
        if component:
            token_exact = (graph.tokens == oracle_tokens).all()
            kv_exact, kv_bytes = _compare_kv_bytes(
                torch, self.model_runner.token_to_kv_pool, snapshots
            )
        block_finite = graph.finite.all() & oracle_finite

        result = GenerationBatchResult(
            logits_output=runner.output_buffers[EXPECTED_CONCURRENCY],
            next_token_ids=graph.tokens[:, -1],
            can_run_cuda_graph=True,
        )
        result.static_c32_token_ids = graph.tokens.clone()
        result.static_c32_oracle_token_ids = (
            oracle_tokens.clone() if oracle_tokens is not None else None
        )
        result.static_c32_block_len = block_len
        result.static_c32_locations = locations
        result.static_c32_validation = torch.stack(
            [
                token_exact,
                position_exact,
                map_exact,
                kv_exact,
                block_finite,
            ]
        )
        result.static_c32_candidate_events = (candidate_start, candidate_end)
        result.static_c32_transition_static = {
            "block_len": block_len,
            "kv_bytes_compared": kv_bytes,
        }
        return result

    def copy_to_cpu(self, return_logprob, return_hidden_states=True):
        if hasattr(self, "static_c32_token_ids"):
            self.static_c32_token_ids = self.static_c32_token_ids.to(
                "cpu", non_blocking=True
            )
            if self.static_c32_oracle_token_ids is not None:
                self.static_c32_oracle_token_ids = (
                    self.static_c32_oracle_token_ids.to("cpu", non_blocking=True)
                )
            self.static_c32_locations = self.static_c32_locations.to(
                "cpu", non_blocking=True
            )
            self.static_c32_validation = self.static_c32_validation.to(
                "cpu", non_blocking=True
            )
        return original_copy(self, return_logprob, return_hidden_states)

    def process_batch_result_decode(self, batch, result):
        global CANDIDATE_DEVICE_MS, DECODE_BOUNDARIES, FINITE, GRAPH_REPLAYS
        global HOST_RESULT_SYNCS, KV_EXACT, POSITION_EXACT, REQUEST_MAP_EXACT
        global TOKEN_EXACT
        if SUMMARY_PATH.exists() or not exact_batch(batch):
            return original_process(self, batch, result)
        if result.copy_done is not None:
            result.copy_done.synchronize()
        DECODE_BOUNDARIES += 1
        HOST_RESULT_SYNCS += 1

        if not TOKENS:
            positions = batch.seq_lens.tolist()
            for row, req in enumerate(batch.reqs):
                index = request_index(req)
                first = int(req.output_ids[-1])
                TOKENS[index] = [first]
                if TARGET_TOKENS == 22 and ARM == "candidate":
                    ORACLE_TOKENS[index] = [first]
                START_POSITIONS[index] = int(positions[row] - 1)

        if not hasattr(result, "static_c32_token_ids"):
            original_process(self, batch, result)
            GRAPH_REPLAYS += 1
            BLOCK_LENGTHS.append(1)
            for req in batch.reqs:
                TOKENS[request_index(req)].append(int(req.output_ids[-1]))
            write_summary(batch)
            return

        token_matrix = result.static_c32_token_ids.tolist()
        oracle_matrix = (
            None
            if result.static_c32_oracle_token_ids is None
            else result.static_c32_oracle_token_ids.tolist()
        )
        token_exact, position_exact, map_exact, kv_exact, finite = (
            bool(value) for value in result.static_c32_validation.tolist()
        )
        TOKEN_EXACT = TOKEN_EXACT and token_exact
        POSITION_EXACT = POSITION_EXACT and position_exact
        REQUEST_MAP_EXACT = REQUEST_MAP_EXACT and map_exact
        KV_EXACT = KV_EXACT and kv_exact
        FINITE = FINITE and finite
        start_event, end_event = result.static_c32_candidate_events
        CANDIDATE_DEVICE_MS += start_event.elapsed_time(end_event)
        block_len = int(result.static_c32_block_len)
        GRAPH_REPLAYS += block_len
        BLOCK_LENGTHS.append(block_len)

        self.metrics_reporter.num_generated_tokens += len(batch.reqs) * block_len
        if self.server_args.enable_metrics:
            self.metrics_collector.increment_decode_cuda_graph_pass(value=True)
        self.token_to_kv_pool_allocator.free_group_begin()
        for row, req in enumerate(batch.reqs):
            values = [int(token) for token in token_matrix[row]]
            req.output_ids.extend(values)
            index = request_index(req)
            TOKENS[index].extend(values)
            if oracle_matrix is not None:
                ORACLE_TOKENS[index].extend(
                    [int(token) for token in oracle_matrix[row]]
                )
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
            **result.static_c32_transition_static,
            "token_exact": token_exact,
            "position_exact": position_exact,
            "request_map_exact": map_exact,
            "kv_byte_exact": kv_exact,
            "finite": finite,
            "output_lengths": sorted({len(req.output_ids) for req in batch.reqs}),
            "locations_unique": (
                result.static_c32_locations.unique().numel()
                == block_len * EXPECTED_CONCURRENCY
            ),
            "seq_lens": sorted(
                {int(value) for value in batch.seq_lens_cpu.tolist()}
            ),
        }
        TRANSITIONS.append(transition)
        append("candidate_supergraph_block", **transition)
        write_summary(batch)

    ScheduleBatch.prepare_for_decode = prepare_for_decode
    TpModelWorker.forward_batch_generation = forward_batch_generation
    GenerationBatchResult.copy_to_cpu = copy_to_cpu
    SchedulerBatchResultProcessor.process_batch_result_decode = (
        process_batch_result_decode
    )
    append("static_c32_supergraph_installed", arm=ARM)


install_frontier()
install_static_executor()
