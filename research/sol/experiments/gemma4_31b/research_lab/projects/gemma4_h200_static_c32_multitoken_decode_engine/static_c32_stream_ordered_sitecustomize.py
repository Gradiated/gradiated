from __future__ import annotations

import pathlib


template_path = pathlib.Path(__file__).with_name("supergraph_template.py")
template = template_path.read_text().replace(
    "\ninstall_frontier()\ninstall_static_executor()\n", "\n"
)
exec(compile(template, str(template_path), "exec"), globals())


class StreamOrderedBlock:
    def __init__(self, torch, runner, template_fb, block_len, input_ids, positions, seq_lens, locations):
        from sglang.srt.model_executor.cuda_graph_runner import build_replay_fb_view

        self.torch, self.runner, self.block_len = torch, runner, block_len
        device = runner.buffers.input_ids.device
        self.input_ids = torch.empty(EXPECTED_CONCURRENCY, dtype=torch.int64, device=device)
        self.positions = torch.empty((block_len, EXPECTED_CONCURRENCY), dtype=torch.int64, device=device)
        self.seq_lens = torch.empty((block_len, EXPECTED_CONCURRENCY), dtype=torch.int32, device=device)
        self.locations = torch.empty((block_len, EXPECTED_CONCURRENCY), dtype=runner.buffers.out_cache_loc.dtype, device=device)
        self.tokens = torch.empty((EXPECTED_CONCURRENCY, block_len), dtype=torch.int64, device=device)
        self.finite = torch.empty(block_len, dtype=torch.bool, device=device)
        self.load(input_ids, positions, seq_lens, locations)
        runner.replay_prepare(template_fb)
        if runner.bs != EXPECTED_CONCURRENCY:
            raise RuntimeError(f"stream ordered padded batch mismatch:{runner.bs}")
        self.fb_view = build_replay_fb_view(
            forward_batch=template_fb, buffers=runner.buffers, bs=EXPECTED_CONCURRENCY,
            raw_bs=EXPECTED_CONCURRENCY, num_tokens=EXPECTED_CONCURRENCY,
            seq_len_fill_value=runner.seq_len_fill_value,
            capture_forward_mode=runner.capture_forward_mode,
            is_encoder_decoder=runner.is_encoder_decoder,
        )
        self.fb_view.out_cache_loc = runner.buffers.out_cache_loc[:EXPECTED_CONCURRENCY]
        self.output, self.backend = runner.output_buffers[EXPECTED_CONCURRENCY], runner.attn_backend
        append("stream_ordered_chain_ready", block_len=block_len)

    def load(self, input_ids, positions, seq_lens, locations):
        self.input_ids.copy_(input_ids)
        self.positions.copy_(positions)
        self.seq_lens.copy_(seq_lens)
        self.locations.copy_(locations)

    def replay(self):
        start, end = self.torch.cuda.Event(enable_timing=True), self.torch.cuda.Event(enable_timing=True)
        append("stream_ordered_enqueue_started", block_len=self.block_len)
        append("supergraph_capture_started", block_len=self.block_len, topology="stream_ordered_no_parent_capture")
        start.record()
        for step in range(self.block_len):
            source = self.input_ids if step == 0 else self.tokens[:, step - 1]
            self.runner.buffers.input_ids[:EXPECTED_CONCURRENCY].copy_(source)
            self.runner.buffers.positions[:EXPECTED_CONCURRENCY].copy_(self.positions[step])
            self.runner.buffers.seq_lens[:EXPECTED_CONCURRENCY].copy_(self.seq_lens[step])
            self.runner.buffers.out_cache_loc[:EXPECTED_CONCURRENCY].copy_(self.locations[step])
            self.backend.init_forward_metadata_out_graph(self.fb_view)
            self.runner.graphs[EXPECTED_CONCURRENCY].replay()
            logits = self.output.next_token_logits[:EXPECTED_CONCURRENCY]
            token = self.torch.argmax(logits, dim=-1)
            self.tokens[:, step].copy_(token)
            self.finite[step].copy_(_selected_finite(self.torch, logits, token))
        end.record()
        return start, end


FixedBlockSupergraph = StreamOrderedBlock
install_frontier()
install_static_executor()
