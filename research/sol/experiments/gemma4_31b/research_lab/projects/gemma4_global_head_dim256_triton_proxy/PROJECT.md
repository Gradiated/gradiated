# Gemma 4 global-head-256 Triton cost proxy

## Question

Without the failed TRTLLM/FlashInfer XQA backend, does changing only Gemma 4's ten full-attention layers from head dimension 512 to 256 still remove at least 5% of canonical H200 service time on the already-supported Triton path?

This is a non-quality-preserving architecture proxy. It can nominate a later weight-surgery/distillation experiment, but cannot establish a deployable checkpoint, output equivalence to the 512-wide model, or production economics.

## Evidence and scope

The prior exact H200 run is terminal for XQA: its first real page-64 E5M2 candidate call faulted with a CUDA illegal address before an oracle, so do not retry, repair, or reinterpret that backend. Before the fault, however, exact current/candidate QKV and output projections plus cached-prefix Triton prompt attention measured `0.08169989766753512` seconds/request of savings, `8.8857%` of the canonical `0.9194573941250042` seconds/request. That measured partial result excludes only decode attention and BF16-to-E5M2 KV writes.

Run one completion discriminator on warm bench `h200-attention-endpoint-e00vbbb709tzxscaan` using the resident pinned SGLang image. Materialize immutable copies of the bound prior runner and result under this project before claiming the bench. Preserve the previous projection and prompt-attention rows; do not replay them. Adapt the runner only to measure:

- current head-512 and candidate head-256 native-GQA Triton decode attention at c32, 4 KV heads, 32 query heads, 4,571-token context, FP8-E5M2 KV, eight splits, and the token-pool/page-1 geometry used by the canonical endpoint;
- current and candidate BF16-to-E5M2 prompt/decode KV writes at the frozen exact shapes;
- finite, nonzero, deterministic candidate output and a numerical oracle against straightforward native-GQA attention over the dequantized E5M2 cache;
- raw timings, exact source/kernel identities, and low-overhead GPU utilization/power/memory telemetry.

Combine those new rows with prior result SHA-256 `5926b98497dd86636aefe3d7385b1ec7ea50e61278c4e33c8eb563b1b828ed85`. Nominate the architecture-only proxy only if the Triton candidate is supported, avoids dense KV repetition, passes its oracle, and the complete conservatively weighted saving remains at least `0.04597286970625021` seconds/request. The frozen partial saving may absorb at most `0.03572702796128491` seconds/request of candidate decode/KV regression before the gate fails. Emit a typed `RESULT.json` and release without teardown.

## Bound resources and limits

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Config SHA-256: `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- Image: `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`; preserve it but do not load or rewrite it for this proxy.
- Prior runner SHA-256: `4648fe19234f8c304a4387ebd512c34430bed5dc04cd9f35bfac3f97436eb62c`.
- Canonical endpoint terminal SHA-256: `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`.

Use `researcher_profile: execution`. Finish by `2026-07-18T22:15:00Z`, use at most 30 wall minutes, 22 H200 minutes, 3 GiB temporary storage, and `$1.25` provider exposure. The existing watchdog protects the bench through `22:30Z`; do not change lifecycle. One pre-invocation wiring repair may repeat only the invalidated operation inside the same claim. Admit no second scientific invocation, XQA retry, backend/dimension/split/page sweep, projection/prompt replay, full endpoint, checkpoint surgery, training, quality run, provider allocation, or lifecycle mutation.
