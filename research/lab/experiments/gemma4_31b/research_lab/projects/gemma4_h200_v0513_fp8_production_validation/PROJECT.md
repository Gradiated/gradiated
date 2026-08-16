# SGLang v0.5.13 dynamic-FP8 production validation

## Decision question

Does the exact SGLang v0.5.13 dynamic-FP8 frontier endpoint preserve the text-only, default non-reasoning quality and feature behavior needed for a credible OpenRouter Gemma 4 31B offering when compared with the same-runtime BF16 control?

The candidate is the first scope-matched endpoint to clear the campaign performance frontier: `0.6979244359999939` seconds/request, 32/32 exact-mix rows, exact cache accounting, 240 quantized target modules and consumers, and a target-prefixed `fp8_scaled_mm` call. At the shared `$3.25/H200-hour` production planning rate this is approximately `$0.13781/M` total tokens for the measured 4,214/358 mix before headroom and non-GPU overhead. Performance is measured; production quality is not.

## Bound candidate and control

Mechanically verify `BINDINGS.json`. The candidate uses exact target `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, SGLang commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, linux/amd64 image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`, the resident exact eight-file checkpoint, dynamic in-memory FP8 linear quantization, FP8-E5M2 KV, dynamic chunking at 2,048, TP1, and no MTP. The paired control changes only target weight quantization to BF16 while retaining the same runtime, checkpoint, KV precision, tokenizer/template, request path, sampling, and feature settings.

The MTP candidate is excluded: its first request consumed that arm and failed in the eager buffer registry. The earlier v0.5.12 quality terminal is not transferable because it tested BF16 weights with only FP8 KV under a different image and failed an over-strict executable control. Reuse only its generic raw-capture and scorer mechanics named in `BINDINGS.json`; inherit no old output, score, policy conclusion, or candidate identity.

## Immediate work

Work offline while `gemma4_h200_qkv_epilogue_fusion` owns or awaits the retained H200. Bind public, licensed GPQA-Diamond and TauBench harness/dataset revisions plus the exact chat/tool schemas into a compact local terminal. Preserve raw benchmark requests, expected-answer or environment identities, deterministic seeds, scorer identities, and request-normalization bytes. Do not invent synthetic substitutes or use aggregate vendor scores. This is one bounded preparation inside the production-validation project, not a separate readiness project.

After the QKV project emits its terminal and releases bench `h200-kernel-frontier-e00pfvrckjvwn7bhet`, claim that retained H200 only if the lifecycle has enough time for the declared run. Stop any incompatible server under the claim, then run sequential same-runtime BF16 and dynamic-FP8 captures through the real `/v1/chat/completions` and tool-call path. Start with the existing small paired feature/NLL suite to catch obvious corruption, but treat Markdown fencing as a recorded structured-output caveat rather than altering semantic benchmark answers. If that gate is valid, continue directly into paired GPQA-Diamond and TauBench without another director admission. Persist raw responses and tool traces before scoring.

## Acceptance and portfolio effect

- Require exact prompt/tokenizer/template identity, finite outputs, deterministic capture where applicable, valid streaming/non-streaming assembly, usage accounting, stop behavior, JSON/tool argument parsing, multi-turn state, and no candidate-specific critical feature regression.
- Require candidate teacher-forced mean NLL to be no more than `0.03` nats/token worse than BF16 over at least 128 scored tokens.
- Report paired GPQA-Diamond accuracy and TauBench task success with counts and bootstrap intervals. The FP8 candidate must not show a statistically credible material regression; any unresolved interval or control failure remains provisional rather than being relabeled a pass.
- A clean paired pass promotes only text-only, default non-reasoning service. Vision/video, reasoning mode, long-horizon reliability, safety policy, and MTP remain separate unvalidated modes.
- A valid FP8 regression closes this representation for production even though its performance result remains scientifically valid. A BF16/control or benchmark-consumer failure is operational evidence to repair once inside the same claim, not candidate evidence.

Do not run a performance sweep, QKV/MTP arm, prompt intervention, adapter, post-training, or provider creation. Use the durable repair handshake for ordinary pre-capture defects and never replay a consumed benchmark split.

## Budgets

- Researcher profile: `execution`.
- Wall clock: 180 minutes.
- Offline preparation: 60 CPU minutes and 6 GiB project-local storage.
- Retained-H200 claim: at most 100 minutes, with 15 minutes reserved for retrieval and release.
- Retrieved artifacts: at most 15 GiB.
- Authorized provider exposure: `$7.00` at the registered `$2.46/hour` experimental rate; no new instance or disk.

Return one atomic terminal with immutable identities, per-arm raw-capture hashes, per-case scores, NLL/reference evidence, GPQA-Diamond and TauBench results, feature boundary, and provider accounting.
