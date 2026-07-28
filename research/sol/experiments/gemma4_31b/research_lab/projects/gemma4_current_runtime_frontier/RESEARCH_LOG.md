# Research log

## 2026-07-22 — activated

Opened as the independent full-stack lane. The required output is a current source-supported GPU endpoint result, not a compatibility report.

## 2026-07-22 — current vLLM candidate and direct H200 launch prepared

Question: which current full-stack runtime is strong enough to spend the one independent H200 arm on?

Action: inspected the live empty GPU pool once, current official vLLM source, its Gemma 4 recipe/model implementation, engine-cache configuration, and the Linux/amd64 image manifest. Bound vLLM main commit `1a659a0c370942bae3c8567902e38bddbbae95f3` and `vllm/vllm-openai@sha256:f0b9a0dc75a9fca3b6811e3279367b2d6a448055a000bfd13859587d74cef268`. Materialized the c32 request runner under this project and prepared `remote_current_vllm_h200.sh`, which records pre-science CUDA state, server identity/logs, GPU telemetry, exact 32×4,214/358 request rows, prefix-cache counters, and a typed terminal.

Evidence: current source has `Gemma4Attention` and current cache configuration lists `fp8_e5m2`, documented as CUDA-supported; the image digest is resolved for linux/amd64. The prior pinned vLLM terminal used a July image and stopped at its E5M2 admission assertion, so it is not a replay of this current source/image.

Interpretation and next move: vLLM is the strongest direct independent candidate, with BF16 checkpoint weights plus FP8-E5M2 KV explicitly labeled as a representation difference from the dynamic-FP8 SGLang frontier. The only present blocker is typed external capacity: the shared pool reports zero benches and the reservation is not durable. On reservation, claim one independent H200 and run the prepared endpoint exactly once; do not add another readiness stage.

## 2026-07-22 — pre-invocation SSH access blocker

Action: materialized the bound 59-GiB immutable checkpoint under `inputs/checkpoint`, verified its index/config/tokenizer hashes, atomically claimed `h200-current-runtime-e00s5ggxfqbn6ctb02`, and launched the bounded outer owner.

Evidence: the provider returned `195.242.29.186` and accepted the SSH host handshake, then rejected `/root/.config/nebius/glm-campaign/ssh_ed25519` for `glmrunner` with `Permission denied (publickey)`. `artifacts/current-vllm-h200-20260722t1231z/OUTER_TERMINAL.json` and the systemd journal record the failure; remote retrieval consequently had no worker terminal. No checkpoint transfer, Docker pull, CUDA call, model load, server start, or scored endpoint request began.

Interpretation: this is a typed remote-access integration blocker, not a candidate outcome or an invocation of the current-vLLM arm. The bench is maintenance-marked for director SSH-key/access repair. The outer owner is patched so a future ordinary pre-invocation access/retrieval fault writes `REPAIR_READY.json` and preserves a claim rather than releasing it.

## 2026-07-22 — current-vLLM FP8-E5M2 terminal incompatibility

Action: reused the resident, hash-verified eight-file checkpoint on the retained H200 and repaired the Docker image-entrypoint duplication in place. The corrected current image started vLLM 0.25.1, loaded the Gemma 4 execution path, and reached its first GPU profile call. The outer owner retained its 45-second heartbeat, retrieved the nested terminal and raw server log, then released the bench available.

Evidence: the live run failed in `vllm/model_executor/layers/attention/attention.py:517` because the Gemma 4 attention path asserts `kv_cache_dtype in {fp8, fp8_e4m3, nvfp4}`. The admitted `--kv-cache-dtype fp8_e5m2` value therefore fails during model profiling, before server readiness or endpoint requests. `INVOCATION_STATE.json` records `candidate_cuda_started: true` and `candidate_science_started: false`; the typed terminal and full trace are retained in `artifacts/current-vllm-h200-20260722t1231z/`.

Interpretation: this is a measured source/CUDA incompatibility for the selected *current* vLLM image, not a replay of the historical July image and not a throughput result. FP8-E4M3 or `fp8` would change the required cache representation, so it is not a repair or substitute arm. The 71.5-minute allocation exposure is approximately $2.94 at $2.46/hour, within the $12.00 reservation. The bench was released available; any next candidate requires a materially distinct director admission.

## 2026-07-22 — current-vLLM FP8-E4M3 c32 endpoint reject

Action: under the director-admitted E4M3 representation change, reused the resident checkpoint and current vLLM 0.25.1 image. The server reported `Using fp8_e4m3 data type to store kv cache`, served `google/gemma-4-31B-it`, and completed the one exact c32 batch. A warm-up request initially carried `stream_options` with `stream=false`; its documented HTTP-400 validation error was repaired in-place without rerunning the producer server or the 32-request batch.

Evidence: all 32 requests returned finite, nonempty text with exact `4214` prompt and `358` completion tokens. Batch service time was `30.053227711` seconds, or `0.939163366 s/request`; output throughput was `381.1903 tokens/s`. The `0.0205364 USD` useful-service cost is recorded at the $2.46/hour metered H200 rate. The request-side metric delta exactly accounts for `134848` prompt tokens, but vLLM did not export an uncached-prompt metric, so the cached/fresh split remains explicitly unavailable rather than inferred.

Interpretation: E4M3 is a real, runnable representation but misses the absolute `0.6381105231 s/request` H200 ceiling by `0.301052843 s/request` (47.2%). This is a measured endpoint reject, not a comparison to the closed E5M2 representation. The H200 was released available at 13:51:18Z with the watchdog reserve intact; estimated cumulative project allocation exposure is about $3.18, below the $12.00 cap.

## 2026-07-22 — runtime portfolio continues

The current-vLLM arm is closed, not the runtime question. Reactivated for a direct current-SGLang endpoint carrying the retained dynamic-FP8/QKV/local-KV stack where source-compatible, then a current TensorRT-LLM candidate if SGLang is not runnable. The next turn must prepare execution rather than summarize compatibility.

## 2026-07-22 — current-SGLang owner active

Action: bound the Gemma-4-capable current SGLang source commit `2813cb6d9a5b6e8fb02435647917e6f1652d7940` and dev-Gemma4 image digest `sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427` to the authoritative retained-stack model, dynamic-FP8-E4M3, FP8-E5M2-KV, TP1, dynamic-chunking, and exact c32 identities. The `h200-continuity-e00hzj9a8khp0fevy5` claim is retained by `gemma4-current-sglang-h200-20260722t1456z.service` with a 45-second heartbeat.

Evidence: the first owner stopped before remote checkpoint, image, CUDA, loader, or endpoint activity because this host has no `rsync` (exit 127). Its remote retrieval proves only small mutable inputs existed. This ordinary launcher defect was repaired in place: the active replacement owner produces a full eight-file SHA-256 manifest, streams the immutable snapshot into a remote incoming directory, verifies it there, and atomically promotes the files before running SGLang.

Interpretation: no current-SGLang scientific arm has begun or been consumed. The durable owner, claim, and partial transfer must be preserved until it supplies a typed terminal or a bounded in-place repair request.

## 2026-07-22 — SGLang warm path repair queued

Action: inspected the retrieved pre-request terminal once and changed only the remote consumer path to `/input/current-sglang/exact_c32_runner.py`. The retry writes a distinct mutable terminal directory so the earlier path-error terminal cannot contaminate the endpoint result; its outer transfer reconciles each of the eight checkpoint hashes and preserves already matching immutable remote files.

Evidence: `h200-continuity-e00hzj9a8khp0fevy5` is exclusively and healthily claimed by the static-FP8 project, with a fresh heartbeat. The current project has no claim and made no remote mutation in this repair turn.

Interpretation and next move: the first SGLang c32 arm remains unconsumed. When static-FP8 releases the bench, atomically claim this same warm bench and start the corrected owner without checkpoint restaging or TensorRT-LLM promotion.

## 2026-07-22 — current-SGLang c32 endpoint reject

Action: claimed the released warm H200, reused the complete hash-verified checkpoint and resident current-SGLang image, corrected only the nested runner path, and ran the one exact c32 endpoint. The owner retrieved the nested terminal and raw server artifacts before releasing the bench ready.

Evidence: current SGLang commit `2813cb6d9a5b6e8fb02435647917e6f1652d7940` on image digest `sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427` reached CUDA and completed all 32 requests with exact 4,214 prompt and 358 completion tokens, nonempty output, and diagnostic responses `READY`, `4`, and structured JSON. The batch took `22.913009542` seconds: `0.716031548` seconds/request, versus the absolute `0.6381105231` ceiling. Current SGLang did not export prompt-cache token deltas, so the cache split is recorded unavailable rather than inferred. Useful service cost was `$0.0156572`; the 157.246-second claim exposure was `$0.1074514` at `$2.46/hour`.

Interpretation: this is a measured endpoint reject (12.21% over ceiling), not the earlier path error. The dynamic-FP8 current-SGLang arm is now consumed; no TensorRT-LLM or additional runtime arm is admitted without a director decision.

## 2026-07-22 — standalone current TensorRT-LLM c32 endpoint reject

Action: bound TensorRT-LLM source HEAD `8341fb1c2abbc49c2cf89f1b6ea659375ebb1820` and the official Linux/amd64 `1.2.0` image digest `sha256:7202108ab373557e0562f78ef3c0f65bdc70e18cc0b040c8d6805a5cde897a0d`. The first owner exposed a missing-GPU help-preflight defect before server creation; repaired only that `--gpus all` flag under the same image, checkpoint, and c32 contract. The corrected owner reused the resident, hash-verified checkpoint and completed the standalone `trtllm-serve` endpoint.

Evidence: `TRTLLM_CONSUMER.json` binds the real TensorRT-LLM server command, image-inspect hash, model response hash, and GPU-enabled help hash. All 32 requests completed with exact 4,214 prompt and 358 completion tokens, nonempty outputs, and diagnostics `READY`, `4`, and structured JSON. Batch service was `22.559067002` seconds, or `0.704970844` seconds/request, versus `0.6381105231`; no prompt-cache token deltas were exported. Useful service cost was `$0.0154154`, with `$0.0670138` claim exposure at `$2.46/hour`.

Interpretation: standalone current TensorRT-LLM is a real, distinct full-stack endpoint—not the closed SGLang TRTLLM-MHA/XQA backend—but misses the ceiling by `0.066860321` seconds/request (10.48%). The arm is consumed and the bench is released ready; no further runtime arm is admitted in this turn.
