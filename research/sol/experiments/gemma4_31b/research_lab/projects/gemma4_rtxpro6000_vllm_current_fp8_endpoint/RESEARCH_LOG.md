# 2026-07-29 — Current vLLM offline owner

Question: can current official vLLM provide an exact, stock dynamic-FP8 Gemma
4 path on sm_120? Action: inspected official vLLM `main`
`6f00a1ae3bd4b86168667bce673998218f461c0f` and implemented the director-bound
retained owner. Evidence: Gemma 4’s conditional checkpoint mapping, dynamic
online FP8 linear/MoE path, BF16 activation allowance, and CUDA FP8 capability
gate all admit the pinned checkpoint and sm_120. Interpretation: supported
offline; execution remains behind the director binding and maintenance claim.
Next: director binds an image digest, resident checkpoint path, and exact
resident SGLang process identity.

## 2026-07-29 — Bound endpoint pre-science terminal

Action: claimed the bound RTX bench, fenced only the recorded resident SGLang
process, and attempted the exact vLLM image through Docker-compatible and
Apptainer/Singularity consumers. Evidence: the retained owner recorded
`IMAGE_CONSUMER_ABSENT`; the pod also lacked an installed `vllm` package and
`ctr`/`runc`. Interpretation: no exact image consumer is available on this
pod, so no vLLM/CUDA/HTTP/c32 sample started. The owner wrote
`external_runtime_image_consumer_unavailable` and released maintenance.

The later retained-native-runtime binding issued at `05:58:00Z` was inspected
after the terminal release at `05:58:31Z`; it assumes the now-released claim
remains live and explicitly forbids reclaim. It is therefore a lifecycle
conflict for the director, not authority to resume native-runtime repair.

## 2026-07-29 — Native vLLM owner offline repair

Action: bound official vLLM `v0.26.0` Linux x86_64 CUDA 12.9 ABI3 wheel
`6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b` from
the published vLLM release, then replaced the unavailable-container launch
path with a resumable `/workspace/vllm-sm120-native-runtime` `uv` environment.
The future owner verifies the wheel before atomic finalization, records vLLM,
Torch and CUDA identities, makes a no-HTTP Gemma4/FP8 import preflight,
supervises the direct server PID, and accepts the already absent predecessor
only after a strict quiescent census. Interpretation: the prior image-consumer
terminal rejects delivery only; an executable official native path is ready
for a fresh director binding. No GPU, SSH, provider, or scientific work ran.

## 2026-07-29 — Retained native runtime repair

Action: after exact wheel install and successful Gemma4/FP8 sm_120 import, the
native server reached online-FP8 model initialization but its inherited
`deep_gemm` extension could not locate `libnvrtc.so.13`. Archived the
zero-request server files, registered the isolated CUDA 13 library path with
the guest dynamic linker, and verified the real `deep_gemm` import without an
environment override. Interpretation: this is an ordinary server-loader
integration repair, not a vLLM support or scientific result; the original
claimed owner remains live and retries the server boundary only.

## 2026-07-29 — FlashInfer sampler repair

Action: retrieved the full failed model-load terminal: after checkpoint load,
FlashInfer's sampler JIT rejected Blackwell `(12, 0)` during warm-up. The
installed vLLM exposes `VLLM_USE_FLASHINFER_SAMPLER=0`; bound that official
fallback in the isolated executable and dynamically verified that vLLM selects
the non-FlashInfer sampler. Interpretation: a pre-request sm_120 integration
defect, with stock FP8/BF16 semantics unchanged; the original owner retains
the claim and has resumed server launch only.

## 2026-07-29 — Endpoint consumer route repair

Action: preserved the completed zero-token `/v1/chat/completions` output at
`endpoint-pair-invalid-chat-completions-20260729t0646z` (run hash
`471205317aac2201eba70cd22ee7808a1bcdefc645acb03f7b980d442da2a946`). Its
raw vLLM validation response requires `messages`, while the immutable admitted
workload carries a token-ID `prompt`; the repair switches only the endpoint
route to `/v1/completions`, preserving payload bytes. The old in-memory owner
could not dispatch that scope and exited after the request, so a hash-bound
detached same-claim consumer-only continuation now reuses the healthy server,
existing tunnel, and a fresh output root. Interpretation: the archived 400s
did not produce tokens or decision-bearing rows; the corrected one-sample run
is in progress and must not be replayed.
