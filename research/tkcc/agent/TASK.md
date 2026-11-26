# Make this forward pass as fast as possible

Model: DeepSeek V4.1 Flash (`deepseek-ai/DeepSeek-V4.1-Flash`, revision `dba1be0a`), served by the production vLLM build (`0.1.dev20904+g179dd0fa9`, V2 model runner, CUDA graphs) at tensor parallel 4 on four NVIDIA B300 GPUs.

Objective: maximize decode tokens per second per user. The score is the geometric mean speedup over the stock forward pass at concurrency 1, 8 and 32. Each request has a real 32,768-token code-and-prose context and generates 128 tokens greedily.

## Edit surface

Write one Python file per candidate. It must define either:

- `install(model, patch, ctx)`: patch anything in the forward pass. Route every change through `patch(obj_or_dotted_module_path, "attr", new_value)` so that teardown can undo it. `ctx` holds `rank`, `tp_size`, `device`, `vllm_config`, `text_model` (the `DeepseekV4Model`) and `job_dir`.
- or `forward(self, input_ids, positions, intermediate_tensors=None, inputs_embeds=None, **kwargs)`, a replacement for `DeepseekV4Model.forward`.

The file is exec'd on every TP rank. CUDA graphs are then recaptured, so your code runs on the measured decode path. You may write Triton, CUDA (`torch.utils.cpp_extension.load_inline`), CuTe DSL or TileLang kernels, call any library in the image, change kernel configurations, fuse operations, and replace collectives. The rules:

- No new quantization or lower precision. Weights must stay bit-identical; this is checked.
- Do not change sampling, the scheduler, batch sizes or the workload.
- Outputs must stay correct. The stock engine is not bit-deterministic under greedy decoding, so the gate is relative to the stock engine's own run-to-run agreement on 32 requests. Agreement on the first 8 tokens and the mean common prefix may each fall at most 25 points below it. The mean |Δlogprob| on the common prefix may be at most 1.5× the stock drift (minimum limit 0.08). The mean logprob of generated tokens may shift by at most 0.10 nats. The 12-layer fast tier produces nonsense text, so its gate only catches crashes, NaNs and gross errors; the slow-tier gate is the real correctness check. Any candidate in the final result is also re-verified on GSM8K accuracy.

The engine source as deployed is in `./vllm/` (read-only copy). The model is `vllm/models/deepseek_v4_1/` (NVIDIA path `nvidia/model.py`, attention, compressor, MoE). On the GPU host the same package lives in `/var/lib/gradiated-kubelet/bundles/58f40e17.../python/lib/python3.12/site-packages`. `examples/noop_candidate.py` shows the format.

## Tools

Run them from this directory.

- `./tkcc submit cand.py --tier fast --name "short description" [--profile]`: the fast tier serves the first 12 of 40 layers. It finishes in a minute or two and catches crashes, hangs and wrong outputs cheaply. `--profile` adds a per-kernel GPU time table.
- `./tkcc submit cand.py --tier slow --name ...`: the slow tier serves all 40 layers. It is authoritative and slower. Only slow-tier results count. Layers 12–39 include ratio-1 attention layers and the candidate-block indexer, which the fast tier lacks.
- `./tkcc status`: queue depth and median job time per tier, and the current best.
- `./tkcc baseline --tier fast|slow`: stock measurements and their noise.
- `./tkcc profile-baseline`: kernel time table for the stock forward pass (fast tier). Profiling leaves CUPTI overhead in the engine process, so the fast engine restarts for about 3–4 minutes after any profiled job or profile-baseline call. Profiling is disabled on the slow tier.
- `./tkcc gpu-run bench.py`: run a standalone Python microbenchmark on the GPU host under the GPU lock, with a 300 s limit. About 25 GiB of each GPU is free while the engines run.
- `./tkcc board read` and `./tkcc board post "..."`: the message board shared with the other agents. Read it before starting each new idea and post what you are trying and what you measured, including failures, so nobody repeats work. Put working candidates in `../shared/` (for example `../shared/<agent>-<idea>.py`) so others can stack on them.

Both tiers share the four GPUs, so measurements queue. Use the waiting time to think, read code and write the next candidate. Measurement noise is about 1–2%; treat smaller gains as unconfirmed until you repeat them.

## Safety

Illegal memory accesses can wedge GPUs, so test risky kernels with `gpu-run` first. Do not run anything on the GPU host except through these tools. Do not touch files outside `/home/tkcc`, and do not stop or restart processes.

Keep working until the deadline you are given: when one idea is done, start the next.
