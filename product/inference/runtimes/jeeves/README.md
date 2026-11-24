# posthog/jeeves runtime

Native SystemOne serving for `posthog/jeeves` on SGLang, behind the gateway's `/v1/systemone` contract. The
[`jeeves-sglang` bundle](../../bundles/jeeves-sglang) packages it. Shared serving code, the contract comparison with
PostHog's server and the parity check are in [`../posthog`](../posthog/README.md).

## Model

- Weights: [`PostHog/jeeves-fp8`](https://huggingface.co/PostHog/jeeves-fp8/tree/vllm), branch `vllm`, at
  `718f9c1aea0753b88fd260045a26e8343fa262d8`, Apache-2.0: the FP8 checkpoint of
  [`PostHog/jeeves`](https://huggingface.co/PostHog/jeeves) `8622b7d1` that PostHog serves. Qwen3.5-9B with a merged
  LoRA, llm-compressor FP8_DYNAMIC (per-channel FP8 weights chosen by GPTQ, per-token FP8 activations; the
  GatedDeltaNet gates `in_proj_a/b`, embeddings and norms stay BF16), the pointer head in `pointer.safetensors`
  (FP32), no `lm_head`, 9.0 GB. Its config names `JeevesForCausalLM` and carries the marker ids and the no-think
  temperature 1.522. Downloaded at the pinned revision into `HF_HOME` (`*.json`, `*.safetensors`, `*.jinja`,
  `*.txt`); no repository code runs.
- Prompt: Jeeves's own format from [`PostHog/jeeves`](https://github.com/PostHog/jeeves) at `954d063d` (MIT), ported
  in `jeeves_prompt.py` with the thinking-marker escaping of `PostHog/hogference`'s server.

### Why FP8 rather than `PostHog/jeeves` BF16

- Memory: the BF16 release is 17.9 GB of shards (about 16 GB without the 2 GB `lm_head`). On an L4's 22 GiB that leaves
  roughly 4 GiB for the GatedDeltaNet state (about 49 MiB a running prompt), the KV cache and the activations of an
  unchunked 16k-token prefill, which the pointer head requires. FP8 is 8.4 GiB and leaves about 10 GiB.
- Safety: the BF16 release ships its pointer head only as `head.pt`, a pickle, which would execute code on load. The
  FP8 branch ships it as safetensors.
- SGLang 0.5.21 loads compressed-tensors FP8 dynamic (linden-1 serves the same format); its W8A8 FP8 scheme needs
  compute capability 8.9, which the L4 has, and uses CUTLASS FP8 GEMMs there with CUDA 12.4 or newer.
- Accuracy: PostHog's measurements against Jeeves's BF16 runtime: these GPTQ weights move probabilities by at most
  0.068 (mean 0.016, three near-tie flips) and change no dataset's accuracy beyond noise.

## Readout

`jeeves_sglang/model.py` is an SGLang model, found through `SGLANG_EXTERNAL_MODEL_PACKAGE=jeeves_sglang`: SGLang's
Qwen3.5 text model with Jeeves's pointer head, ported from hogference's vLLM model (`jeeves/server/jeeves_vllm.py`).
A question's tokens are its prompt (chat template with thinking on, state, question, options), the empty thinking,
`</think>`, the options again, each closed by `</opt>`, and `<decide>`. In each extend step the model finds the
requests ending in `<decide>` (`jeeves_sglang/readout.py`) and scores option i as the scaled dot product of the head's
query of the final hidden state at `<decide>` with its key of the hidden state at the i-th `</opt>` after `</think>`.
The logits processor returns the scores as the logits of token ids 0 to 254 (other ids 0) through a head with no
weight; the adapter reads them with `token_ids_logprob`, divides by 1.522 and softmaxes. A `noul` reads options
(no, yes). No `lm_head` is allocated. hogference's fused FP8 kernels, last-layer split and prefix-state connector are
not ported.

The head needs a question's options and `<decide>` in one forward step, so SGLang runs without chunked prefill and
without radix cache (a cache hit would leave the options out of the step). A question read from an incomplete step
gets NaN scores, which the adapter refuses with a 500 rather than answering. For batches with at least four scored questions, when each has
at least 2,048 tokens and their total exceeds one 16,385-token prefill step, the adapter submits them one at a time. Confidence is the top probability, as
PostHog reports it; usage counts every question's whole prompt, nothing cached.

## Limits

- 16,384 tokens a prompt and 65,536 a request, else 422; never truncated.
- 1 to 255 options (one pass, as Jeeves) and 1 to 1,024 questions; up to 8 requests at once, then 429.
- No thinking: PostHog measured 19 to 92 s for a three-question request with it.
- SGLang: one GPU, `--mem-fraction-static 0.80`, up to 32 running prompts, `--max-prefill-tokens` 16,385, no CUDA
  graphs.

## Placement

One NVIDIA L4 (24 GB, compute 8.9) a replica, on a g6.xlarge (4 vCPU, about 14 GiB allocatable host memory). The
release is pinned in `product/inference/gpu/runtimes.json` under the private runtime model ID
`posthog/jeeves-qualification`, served as `posthog/jeeves`: `gpus` 1, `active_requests` 8, `cpu` "3", `memory` and
`request_memory` "12Gi", `startup_timeout` 1800. The production pool `jeeves-l4` (`models.json`) runs two replicas on
the four AWS L4 hosts reserved for `posthog`.

## Verification

- CPU: `test_jeeves_service.py` (fake tokenizer and engine): prompt rendering and marker escaping, the step readout
  plan, answer shapes, temperature readout, limits, engine failures and the parity cases.
- Offline, with the checkpoint's tokenizer and `transformers` 5.12.1: all 46 reference prompts have the reference's
  token counts and the same token ids as Jeeves's own `Encoder`; the model's `option_scores` and head match a direct
  pointer-head computation with SGLang 0.5.21 and CPU torch (not committed; it needs SGLang installed).
- Build: `verify-build.py` checks the pins, the SGLang interfaces the model relies on (external model package, the
  quant-method head path of the logits processor, the step metadata), the SGLang flags against SGLang's parser and the
  answer format for 1 to 255 options. It needs no GPU.
- GPU (not yet run): start-up and weight loading on an L4, `parity.py --model posthog/jeeves`, and qualification.

## Known parity caveats

- The reference is Jeeves's own BF16 runtime; FP8 moved near-ties by up to 0.13 in PostHog's runs, within the 0.15
  gate. SGLang's FP8 GEMMs and GDN kernels differ from vLLM's and have not been measured.
- Answers move slightly with batch composition, as PostHog observed for vLLM.
- Qualification's request is close to the reference's "I was billed twice..." and "charged a late fee" cases, which
  Jeeves answers billing at 0.9996 and 0.994, so `billing` is expected (inferred, not measured).
