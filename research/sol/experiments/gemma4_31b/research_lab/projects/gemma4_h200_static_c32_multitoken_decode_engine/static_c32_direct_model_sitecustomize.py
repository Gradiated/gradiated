from __future__ import annotations

import copy
import pathlib


GRAPH_MEMORY: list[dict[str, object]] = []
template_path = pathlib.Path(__file__).with_name("supergraph_template.py")
template = template_path.read_text()
template = template.replace(
    "\ninstall_frontier()\ninstall_static_executor()\n", "\n"
)
template = template.replace(
    '"model_graph_replays": GRAPH_REPLAYS,',
    '"model_graph_replays": GRAPH_REPLAYS,\n'
    '        "raw_model_forwards": GRAPH_REPLAYS,\n'
    '        "execution_body": "pinned_runtime_raw_model_forward",\n'
    '        "graph_memory": GRAPH_MEMORY,',
)
template = template.replace(
    "runner.buffers.positions[:EXPECTED_CONCURRENCY] == positions[-1]",
    "graph.position_exact(positions, seq_lens, template_fb.req_pool_indices)",
)
template = template.replace(
    "logits_output=runner.output_buffers[EXPECTED_CONCURRENCY],",
    "logits_output=graph.output,",
)
exec(compile(template, str(template_path), "exec"), globals())


def memory_row(torch, phase: str, block_len: int) -> dict[str, object]:
    free_bytes, total_bytes = torch.cuda.mem_get_info()
    return {
        "phase": phase,
        "block_len": block_len,
        "free_bytes": int(free_bytes),
        "total_bytes": int(total_bytes),
        "allocated_bytes": int(torch.cuda.memory_allocated()),
        "reserved_bytes": int(torch.cuda.memory_reserved()),
        "max_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "max_reserved_bytes": int(torch.cuda.max_memory_reserved()),
    }


def topology_blocker(torch, block_len: int, error: BaseException) -> None:
    row = memory_row(torch, "graph_instantiation_failed", block_len)
    value = {
        "schema_version": 1,
        "classification": "component_topology_reject_graph_memory_shortfall",
        "pass": False,
        "block_geometry": [7, 8, 6],
        "failed_block_len": block_len,
        "concurrency": EXPECTED_CONCURRENCY,
        "error": {"type": type(error).__name__, "message": str(error)},
        "memory": row,
        "geometry_changed": False,
    }
    atomic_json(AUDIT_PATH.parent / "DIRECT_MODEL_TOPOLOGY_BLOCKER.json", value)
    append("direct_model_graph_memory_shortfall", **value)


class DirectModelBlock:
    def __init__(
        self,
        torch,
        runner,
        template_fb,
        block_len,
        input_ids,
        positions,
        seq_lens,
        locations,
    ):
        from sglang.srt.layers.attention.triton_backend import TritonAttnBackend
        from sglang.srt.layers.dp_attention import (
            DpPaddingMode,
            set_dp_buffer_len,
            set_is_extend_in_batch,
        )
        from sglang.srt.model_executor.cuda_graph_runner import (
            get_global_graph_memory_pool,
            model_capture_mode,
        )
        from sglang.srt.model_executor.forward_context import (
            ForwardContext,
            forward_context,
        )

        self.torch = torch
        self.runner = runner
        self.block_len = block_len
        self.graph = torch.cuda.CUDAGraph()
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
        self.request_indices = template_fb.req_pool_indices.clone()
        self.tokens = torch.empty(
            (EXPECTED_CONCURRENCY, block_len), dtype=torch.int64, device=device
        )
        self.finite = torch.empty(block_len, dtype=torch.bool, device=device)
        self.load(input_ids, positions, seq_lens, locations)
        self.backends = []
        self.forward_batches = []
        model_runner = runner.model_runner

        before = memory_row(torch, "before_step_state", block_len)
        GRAPH_MEMORY.append(before)
        append("direct_model_graph_memory", **before)
        try:
            for step in range(block_len):
                backend = TritonAttnBackend(model_runner, skip_prefill=True)
                backend.init_cuda_graph_state(
                    EXPECTED_CONCURRENCY, EXPECTED_CONCURRENCY
                )
                fb = copy.copy(template_fb)
                fb.batch_size = EXPECTED_CONCURRENCY
                fb.input_ids = (
                    self.input_ids if step == 0 else self.tokens[:, step - 1]
                )
                fb.positions = self.positions[step]
                fb.seq_lens = self.seq_lens[step]
                fb.seq_lens_cpu = self.seq_lens[step].to("cpu")
                fb.orig_seq_lens = self.seq_lens[step]
                fb.req_pool_indices = self.request_indices
                fb.out_cache_loc = self.locations[step]
                fb.seq_lens_sum = int(self.seq_lens[step].sum().item())
                fb.next_token_logits_buffer = torch.empty_like(
                    runner.buffers.next_token_logits_buffer[
                        :EXPECTED_CONCURRENCY
                    ]
                )
                fb.dp_padding_mode = DpPaddingMode.get_default_mode_in_cuda_graph()
                fb.dp_local_start_pos = None
                fb.dp_local_num_tokens = None
                self.backends.append(backend)
                self.forward_batches.append(fb)

            for backend, fb in zip(self.backends, self.forward_batches):
                with forward_context(ForwardContext(attn_backend=backend)):
                    runner.tbo_plugin.capture_one_batch_size(
                        fb, num_tokens=EXPECTED_CONCURRENCY
                    )
                    backend.init_forward_metadata_out_graph(
                        fb, in_capture=True
                    )

            after_setup = memory_row(torch, "after_out_graph_setup", block_len)
            GRAPH_MEMORY.append(after_setup)
            append("direct_model_graph_memory", **after_setup)

            def run_once():
                output = None
                for step, (backend, fb) in enumerate(
                    zip(self.backends, self.forward_batches)
                ):
                    with forward_context(ForwardContext(attn_backend=backend)):
                        backend.init_forward_metadata_in_graph(fb)
                        fb.dp_local_start_pos = fb.dp_local_num_tokens = None
                        set_dp_buffer_len(
                            None,
                            EXPECTED_CONCURRENCY,
                            fb.dp_padding_mode.is_max_len(),
                            None,
                        )
                        set_is_extend_in_batch(False)
                        output = model_runner.model.forward(
                            fb.input_ids,
                            fb.positions,
                            fb,
                        )
                    logits = output.next_token_logits[:EXPECTED_CONCURRENCY]
                    token = torch.argmax(logits, dim=-1)
                    self.tokens[:, step].copy_(token)
                    self.finite[step].copy_(
                        _selected_finite(torch, logits, token)
                    )
                return output

            torch.cuda.synchronize()
            with model_capture_mode(), torch.inference_mode():
                for _ in range(2):
                    run_once()
                    torch.cuda.synchronize()
                    for backend in self.backends:
                        backend.on_after_cuda_graph_warmup()

                after_warmup = memory_row(
                    torch, "after_official_warmup", block_len
                )
                GRAPH_MEMORY.append(after_warmup)
                append("direct_model_graph_memory", **after_warmup)
                append(
                    "supergraph_capture_started",
                    block_len=block_len,
                    topology="direct_raw_model_forward_parent_graph",
                    child_graph_replay=False,
                    step_specific_attention_backends=len(self.backends),
                )
                self.output = runner._capture_graph(
                    self.graph,
                    get_global_graph_memory_pool(),
                    runner.stream,
                    run_once,
                )
            torch.cuda.synchronize()
            after_capture = memory_row(
                torch, "after_graph_instantiation", block_len
            )
            GRAPH_MEMORY.append(after_capture)
            append("direct_model_graph_memory", **after_capture)
            append(
                "supergraph_capture_complete",
                block_len=block_len,
                raw_model_forwards=block_len,
                child_graph_replay=False,
            )
        except (torch.cuda.OutOfMemoryError, RuntimeError) as error:
            if isinstance(error, torch.cuda.OutOfMemoryError) or "out of memory" in str(
                error
            ).lower():
                topology_blocker(torch, block_len, error)
            raise

    def load(self, input_ids, positions, seq_lens, locations):
        self.input_ids.copy_(input_ids)
        self.positions.copy_(positions)
        self.seq_lens.copy_(seq_lens)
        self.locations.copy_(locations)

    def position_exact(self, positions, seq_lens, request_indices):
        return (
            (self.positions == positions).all()
            & (self.seq_lens == seq_lens).all()
            & (self.request_indices == request_indices).all()
        )

    def replay(self):
        start = self.torch.cuda.Event(enable_timing=True)
        end = self.torch.cuda.Event(enable_timing=True)
        start.record()
        self.graph.replay()
        end.record()
        return start, end


FixedBlockSupergraph = DirectModelBlock
install_frontier()
install_static_executor()
