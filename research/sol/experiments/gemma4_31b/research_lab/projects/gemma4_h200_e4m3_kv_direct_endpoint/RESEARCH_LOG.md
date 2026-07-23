# Research log

## 2026-07-23 — E4M3 KV direct endpoint closed

Question: does changing only the retained SGLang v0.5.13 KV cache from E5M2 to E4M3 preserve the exact c32 serving path and improve the current `0.6743258590 s/request` control?

Action: verified the director binding and durable $8 reservation, materialized the bound launcher bytes under this project, claimed `h200-sync-linear-e00vhh6h29fj68x91g`, and reused its manifest-verified read-only checkpoint, pinned image, and caches. The sole candidate used `--kv-cache-dtype fp8_e4m3` with Triton explicitly bound for prefill and decode; no FA3, control replay, workload change, or checkpoint copy occurred. Two pre-invocation owner defects (local manifest directory enumeration and a telemetry argument collision) were repaired under the same retained claim before CUDA. The candidate then ran once; its raw terminal, response bytes, server log, runtime audit, telemetry, and compact archive were retrieved before release.

Evidence: the E4M3 server log records `torch.float8_e4m3fn` KV allocation, while `candidate.server-args.txt` binds stock Triton for both phases. The nonzero coherence discriminator passed its three fixed E5M2-reference prompts. The c32 candidate completed 32/32 finite, nonempty responses at the exact 4,214/358 token geometry with `17,120` cached and `117,728` fresh tokens. It measured `22.4730969150` batch seconds or `0.7022842786 s/request`, a `-4.1461%` movement versus the persisted `0.6743258590` E5M2 control. The candidate QKV audit was absent, so the full retained-stack identity is unproven even though E4M3 allocation, runtime source identity, and Triton arguments are directly observed. Cumulative conservative provider exposure is `$0.1582940733`.

Interpretation: this is a consumed `close`, not a valid FA3 comparator. The observed E4M3 endpoint is slower and, independently, lacks the required QKV path proof; neither result authorizes a replay or a FA3 launch from this project. The healthy E4M3 server, checkpoint, image, and caches were retained and the bench released ready.
