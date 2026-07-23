# E4M3 local-FA3 / global-Triton hybrid attention on H200

## Question

Can one exact source-routed attention backend use Hopper FlashAttention-3 for Gemma 4's 50 local head-dimension-256 layers while retaining Triton for the ten global head-dimension-512 layers, reducing the measured local-attention boundary enough to improve the exact current c32 endpoint?

## Causal hypothesis

The current profile assigns 15.312032% of whole-request wall time to the local attention kernel. Its exact local path has 32 query heads, 16 KV heads, head dimension 256, a 1,024-token window, FP8-E5M2 KV, 255 registers/thread, and one residency-limited CTA/SM. Pinned SGLang source explicitly falls back from FA3 only when KV is E5M2 and says FA3 supports FP8-E4M3. Separate source evidence says Hopper FA3 covers head dimension at most 256, while the model's global dimension 512 must remain outside that backend.

The intervention is therefore one backend/dataflow change, not another Triton tile or register experiment: use the direct project's E4M3 KV representation, route only actual paged local prefill/decode attention to FA3, and keep actual paged global attention on the unchanged Triton consumer. The prediction is at least a 35.1% reduction of the scope-matched local-attention interval union, enough in the E5M2 control scope to bridge `0.6743258590313417` to `0.6381105231 s/request`; a smaller operationally simple endpoint gain remains retainable.

## Immutable identity and evidence

- Model/checkpoint/runtime/workload are identical to `../gemma4_h200_e4m3_kv_direct_endpoint/DIRECTOR_BINDING.json`.
- Exact runtime image: `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Profile attribution: `../gemma4_h200_v0513_fp8_qkv_residual_profile/artifacts/residual-profile-20260720t0821z/ATTRIBUTION.json`, SHA-256 `f841db590dbe6f2e6b4fb91048e8132c3807f0321310e1e0b70a3957ac99ab48`.
- Backend/geometry support evidence: `../h100_hybrid_attention_kernel_mechanism/MECHANISM.json`, SHA-256 `3960c453e88b1a12e01351d2062dbaa7f8a800e63fe6674e997ddbbcfeebdda1`; only its pinned-source FA3/E4M3/head-dimension facts transfer, not H100 timing or economics.
- Local source/geometry evidence: `../gemma4_h200_local_window512_codesign/EVIDENCE_BINDING.json`; retain the original 1,024-token window. The consumed 512-window proxy and the earlier value-split, two-stage, Stream-K, register-cap, and tile candidates remain closed.
- Comparator dependency: consume the typed E4M3-Triton terminal from `gemma4_h200_e4m3_kv_direct_endpoint`; do not replay its endpoint.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` mechanically bind the authoritative static inputs. The researcher must add a content-addressed live source binding for the actual v0.5.13 FA3, Triton, hybrid-router, and KV producer/consumer symbols before mutation.

## Immediate experiment

Use `$kernel-research`. Prepare offline immediately while the direct E4M3 project uses the shared bench. Inspect the pinned image/source and bind the actual paged producer, local FA3 consumer, global Triton consumer, backend-selection/router, FP8 scales/layout, prefill/decode shapes, and fallback guards. Implement exactly one source-routed hybrid. If the stock router cannot select per layer, the minimal router implementation itself is within scope; a backend or flag sweep is not.

After the direct E4M3 project emits its terminal and releases `h200-sync-linear-e00vhh6h29fj68x91g`, consume that terminal. Close without claiming only if E4M3 is incoherent/unsupported or even perfect removal of its measured local boundary cannot beat the E5M2 frontier. Otherwise claim the same warm bench and reuse its E4M3 server/checkpoint/image/caches.

First run one correctness-bearing exact-consumer component pair: E4M3 Triton local attention versus E4M3 FA3 local attention on the actual paged layouts and the scope-matched prefill/decode geometries. Require real KV producer/scale consumption, nonzero inputs, finite consumed outputs, an explicit numerical oracle against the Triton E4M3 result, stable randomized timing, and path proof that local layers use FA3 while global layers remain Triton. Record local interval-union latency, launch count, fallback count, and only the minimum counter evidence needed to distinguish backend execution and the predicted reduction.

Promote immediately to one profiler-off exact c32 hybrid candidate only if the component plus direct E4M3 endpoint yields a conservative whole-request path below `0.6743258590313417 s/request`; crossing `0.6381105231` is the main goal. Reuse the direct project's persisted E4M3 terminal as control. Require 32/32 exact 4,214/358 usage, exact 17,120/117,728 cache accounting, sane outputs, no fallback/reload, and layer-specific backend proof. Collect a minimum candidate trace only after a positive endpoint when needed to verify the predicted boundary change.

## Stop rules

Close after the sole candidate on unsupported actual paged E4M3 FA3 semantics, numerical failure, component regression, insufficient conservative bound, invalid endpoint accounting, or endpoint regression. Do not try global FA3, E5M2 conversion, window changes, head-dimension changes, FA3 parameters, Triton tiles, alternate backends, or a second candidate. A performance survivor is still representation-changing and cannot become production-eligible without later quality/feature validation.

## Resources

- Researcher profile: `deep` until the exact router/producer/geometry mechanism and component result are established; switch to `execution` only if routine endpoint dispatch remains.
- One retained H200, sequentially after the direct E4M3 project; at most 120 claimed GPU-minutes and three wall hours from first claim.
- Provider exposure charged to the existing bench; project authorization `$12.00`.
- At most 8 GiB new artifacts/build outputs; reuse the read-only checkpoint and retained image/caches.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
