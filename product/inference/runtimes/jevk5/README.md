# posthog/jevk5 runtime

Native SystemOne serving for `posthog/jevk5` on SGLang, behind the gateway's `/v1/systemone` contract. The
[`jevk5-sglang` bundle](../../bundles/jevk5-sglang) packages it. Shared serving code, the contract comparison with
PostHog's server and the parity check are in [`../posthog`](../posthog/README.md).

## Model

- Weights: [`alibiserikbay/JevK5`](https://huggingface.co/alibiserikbay/JevK5) at
  `c4f7fdb3aeab5582336406e78d3bef11bf98833d` (JevK5 v0.3), Apache-2.0: Qwen3.5-4B (GatedDeltaNet linear attention in
  24 of 32 layers) with a distilled LoRA merged, one BF16 `model.safetensors` of 8.4 GB, and `jevk5_config.json`
  (`temperature` 1.22, `knockout_temperature` 0.93). Downloaded at the pinned revision into `HF_HOME` at start
  (`*.json`, `*.safetensors`, `*.jinja`); no repository code runs.
- Prompt and readout: [`allebee/jevk5`](https://github.com/allebee/jevk5) at `7b97499c` (0.3.2). Its `jevk5/prompt.py`
  is vendored byte for byte as `jevk5_prompt.py` (sha256 pinned in `service.py` and checked by the tests and the
  build), with its `LICENSE.jevk5` (Apache-2.0) and `NOTICE.jevk5`.
- Served in BF16, as PostHog serves it: its parity table puts BF16 closest to the upstream runtime.
- The checkpoint names its weights `model.language_model.*`, as Qwen3.5's vision-language checkpoints do, but declares
  the text-only `Qwen3_5ForCausalLM`. SGLang 0.5.21's text loader matches none of those names and silently leaves every
  layer uninitialised, so every logit is NaN (measured on the L4 hosts, 2026-11-23; `transformers` loads them).
  `jevk5_sglang/model.py` (`JevK5ForCausalLM`, an SGLang external model package selected with
  `--json-model-override-args`) renames them before the stock loader and refuses to start if any parameter is unloaded.

## Readout

Each question is upstream's prompt (fixed system instruction; the evidence, criterion and lettered options as JSON;
Qwen3.5's chat template with thinking off), answered by one uppercase letter A to P. SGLang computes one next token
per prompt at temperature 0 and returns the letters' log probabilities, which differ from the raw logits by one
constant per prompt; the answer is the softmax of those divided by 1.22. A `noul` reads options (true, false). A
question with more than 16 options takes upstream's knockout (`spread`, method `knockout`): its options in
ceil(n / 16) groups, then a final over the groups' best, sharpened by 0.93. All the questions' current passes go to
SGLang in one batched call; upstream's own `spread` is replayed over the passes read so far to find the next ones.
The LM head runs in FP32 (`--enable-fp32-lm-head`).

Each scored request uses SGLang's pod-local `extra_buffer` Mamba radix cache (patched into the bundle for
`JevK5ForCausalLM`), saving an aligned GatedDeltaNet checkpoint at the shared evidence prefix boundary on a cold
forward. On a cold multi-pass request over a state of at least 64 tokens, the adapter submits the first pass to
populate the checkpoint and then batches the remaining passes; warm states batch all passes together. Confidence is
the top probability, as PostHog reports it. Usage counts every pass's whole prompt, as upstream does, with nothing
reported as cached.

## Limits

- 16,384 tokens a prompt (JevK5's own limit) and 65,536 a request across its passes, else 422; never truncated.
- 1 to 255 options (the gateway's bound) and 1 to 1,024 questions; up to 8 requests at once, then 429.
- SGLang: one GPU, `--mem-fraction-static 0.80`, up to 64 running prompts, prompts prefilled whole
  (`--max-prefill-tokens` and `--chunked-prefill-size` 16,385), `--mamba-radix-cache-strategy extra_buffer`,
  `--disable-overlap-schedule`, decode CUDA graphs disabled, breakable prefill CUDA graphs for sizes 64..1,024.

## Placement

One NVIDIA L4 (24 GB, compute 8.9) a replica, on a g6.xlarge (4 vCPU, about 14 GiB allocatable host memory). The
release is pinned in `product/inference/gpu/runtimes.json` under the private runtime model ID
`posthog/jevk5-qualification`, served as `posthog/jevk5`: `gpus` 1, `active_requests` 8, `cpu` "3", `memory` and
`request_memory` "12Gi", `startup_timeout` 1800. The production pool `jevk5-l4` (`models.json`) runs two replicas on
the four AWS L4 hosts reserved for `posthog`.

## Verification

- CPU: `test_jevk5_service.py` (fake tokenizer and engine): answer shapes, temperature readout, knockout passes against
  upstream's `spread`, limits, engine failures, and that every parity case is a valid gateway request.
- Build: `verify-build.py` checks the pins, the vendored prompt's hash, SGLang's Qwen3.5 text model, the SGLang flags
  against SGLang's own argument parser, and the answer format for 1 to 255 options. It needs no GPU.
- GPU (not yet run): start-up on an L4, `parity.py --model posthog/jevk5`, and worker qualification. PostHog
  measured 0.005 mean and 0.020 max |Δp| for BF16 on vLLM; SGLang's kernels have not been measured.

## Known parity caveats

- Kernel differences move probabilities slightly; the knockout amplifies them at near-ties at a group's cut-off,
  where a different finalist changes the final (PostHog saw 0.70 against 0.89 on 40 near-identical names).
- Cached prefixes are exact up to kernel rounding; PostHog measured shared-state answers within batching noise.
- Qualification asks `billing` or `technical` for "I was charged twice. This is a billing problem."; JevK5 answers
  the reference's closest cases ("I was billed twice...", "charged a late fee") with billing at 0.99 and 0.97, so
  `billing` is expected (inferred, not measured).
