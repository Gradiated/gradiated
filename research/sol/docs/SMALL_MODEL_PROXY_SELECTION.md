# Small-model proxy selection for model–memory co-design

**Decision, 2026-07-12:** keep **Qwen3-0.6B** as the current local, quality-bearing proxy. Use it for model-weight interventions, exact tensor/byte accounting, dense KV policies, serving controls, and end-to-end experiment plumbing. Make **NOSA-1B** the first future single-GPU proxy, because it is the only candidate here trained specifically around sparse attention, locality, and KV offload. The tiny DeepSeek-V3.2 fixture is source-only schema material, not an executable performance proxy. Idiap's trained 1.4B hybrid NSA checkpoint is a useful second sparse mechanism control, not the primary offload proxy.

No candidate can approve performance transfer to GLM-5.2. A small model may reject a mechanism cheaply or justify a GLM-scale experiment; it cannot validate GLM-specific dollars per token.

## Target boundary

The pinned [GLM-5.2 manifest](https://huggingface.co/api/models/zai-org/GLM-5.2/revision/b4734de4facf877f85769a911abafc5283eab3d9?blobs=true) reports 753,329,940,480 parameters. Its [configuration](https://huggingface.co/zai-org/GLM-5.2/blob/b4734de4facf877f85769a911abafc5283eab3d9/config.json) has 78 layers, 256 routed experts with top-8 activation plus one shared expert, MLA ranks, a 2,048-token DSA selector, a repeating full/shared indexer pattern with frequency four, one multi-token-prediction layer, and a 1,048,576-token maximum position setting. A proxy is therefore judged against five mechanisms: routed MoE, MLA/DSA sparse selection, cross-layer or temporal locality, MTP, and tiered/offloaded state.

Scores below assess **usable execution coverage**, not name similarity.

- Structural scores: **0** absent; **1** schema, incomplete path, or related-but-different mechanism; **2** executable close analogue.
- Operational scores: **0** unusable; **1** weak; **2** conditional; **3** strong. For CUDA independence, 3 means the relevant path has no CUDA requirement.

| Candidate | MoE / top-k experts | MLA / DSA or sparse selection | Cross-layer / temporal locality | MTP | Tier / offload relevance |
|---|---:|---:|---:|---:|---:|
| Qwen3-0.6B | 0 | 0 | 0 | 0 | 1 |
| NOSA-1B | 0 | 1 | 1 | 0 | 2 |
| tiny-random DeepSeek-V3.2 | 1* | 1* | 0 | 1* | 1* |
| Idiap Gated DeltaNet + NSA 1.4B | 0 | 1 | 1 | 0 | 1 |

The asterisks are schema-only. The tiny fixture does not execute those mechanisms correctly at its pinned revision.

| Candidate | Task-quality authority | License clarity | Format / local size | CPU | MPS | CUDA-independent | One GPU |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-0.6B | 2 | 3 | 3 | 3 | 2 | 3 | 3 |
| NOSA-1B | 2 | 2 | 1 | 0 | 0 | 0 | 2 |
| tiny-random DeepSeek-V3.2 | 0 | 1 | 3 | 1 | 1 | 1 | 0 |
| Idiap Gated DeltaNet + NSA 1.4B | 1 | 3 | 2 | 0 | 0 | 0 | 2 |

## Evidence by candidate

### Qwen3-0.6B — current local proxy

Pin **Qwen/Qwen3-0.6B@c1899de289a04d12100db370d81485cdf75e47ca**. The official [manifest](https://huggingface.co/api/models/Qwen/Qwen3-0.6B/revision/c1899de289a04d12100db370d81485cdf75e47ca?blobs=true) reports 751,632,384 BF16 parameters and a 1,503,300,328-byte safetensors file with SHA-256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`. The [configuration](https://huggingface.co/Qwen/Qwen3-0.6B/blob/c1899de289a04d12100db370d81485cdf75e47ca/config.json) is a standard dense 28-layer Qwen model with hidden size 1,024, 16 query heads, and eight KV heads. The repository includes an [Apache-2.0 license](https://huggingface.co/Qwen/Qwen3-0.6B/blob/c1899de289a04d12100db370d81485cdf75e47ca/LICENSE).

This is the only candidate already tied to local first-party quality and runtime evidence. The exact checkpoint has loaded and generated through local vLLM CPU execution in the [throughput smoke](../validation/results/qwen3-0.6b-vllm-cpu-throughput-v1.json), and model edits have crossed both [held-out WikiText](../validation/results/qwen3-0.6b-int4-o-gate-up-wikitext2-sequential4096-bf16-v1.json) and [exact-source PIQA](../validation/results/qwen3-0.6b-int4-o-gate-up-piqa256-bf16scale-v1.json) boundaries. MPS is plausible through the standard PyTorch/Transformers path but has not been qualified here. The [repeatability campaign](../validation/results/qwen3-0.6b-vllm-cpu-repeatability-v1.json) remains host-contamination-blocked, so the model is locally executable but not yet a calibrated serving-performance oracle.

It can validate weight-format and selective-weight changes, dense attention/KV byte accounting, task sensitivity, experiment reproducibility, and stack interfaces. It cannot validate expert routing, MLA compression, DSA selection, shared indexers, MTP acceptance, or learned offload locality. Dense tier-policy results are scheduler experiments, not validation of a sparse model change.

### NOSA-1B — future single-GPU proxy

Pin **openbmb/NOSA-1B@7bdc33fbc1bc80b76b29689ba35ff6a7991b7dee**. The official [manifest](https://huggingface.co/api/models/openbmb/NOSA-1B/revision/7bdc33fbc1bc80b76b29689ba35ff6a7991b7dee?blobs=true) reports 3,245,641,146 repository bytes and a 3,244,459,942-byte PyTorch checkpoint with LFS SHA-256 `831236605310bdfded1fc5959dfecd033b48a0aa3ebdd2aa28f19d0ecf5ce4aa`. Its [configuration](https://huggingface.co/openbmb/NOSA-1B/blob/7bdc33fbc1bc80b76b29689ba35ff6a7991b7dee/config.json) has 28 layers, hidden size 2,048, 16 query heads, and two KV heads.

The official [model card](https://huggingface.co/openbmb/NOSA-1B/blob/7bdc33fbc1bc80b76b29689ba35ff6a7991b7dee/README.md) describes a trained sparse-attention mechanism with an explicit locality constraint for KV-cache offloading and released 1B/3B/8B checkpoints. That gives it direct relevance to the business hypothesis. The checkpoint is not locally viable: its pinned [model code](https://huggingface.co/openbmb/NOSA-1B/blob/7bdc33fbc1bc80b76b29689ba35ff6a7991b7dee/modeling_llama_long_infllmv2.py) calls InfLLM-v2 sparse CUDA functions, while [cis_pooling.py](https://huggingface.co/openbmb/NOSA-1B/blob/7bdc33fbc1bc80b76b29689ba35ff6a7991b7dee/cis_pooling.py) imports Triton unconditionally. The official [runtime instructions](https://github.com/thunlp/NOSA/blob/1cbee77d607f9051b206a09c862bea28becb9e67/README.md) use a prepared Docker image, CUDA architecture compilation, and NOSI installation. Downloading 3.24 GB on this Mac would not make the sparse path runnable.

License handling needs a component bill of materials. The Hugging Face checkpoint metadata says Apache-2.0 but contains no license file; the pinned official code repository carries an [MIT license](https://github.com/thunlp/NOSA/blob/1cbee77d607f9051b206a09c862bea28becb9e67/LICENSE). This is not evidence of incompatibility, but it prevents a maximum clarity score.

NOSA can test whether learned sparse locality converts host/device traffic into real throughput and cost savings. It cannot test GLM's routed experts, MLA cache representation, DSA indexer mathematics or sharing pattern, or MTP. Its model card says matched FullAttn, InfLLMv2, and DMA models were trained but asks users to contact the authors for unreleased baselines; without the matched FullAttn-1B control, NOSA cannot isolate the causal gain from the architecture change.

### tiny-random DeepSeek-V3.2 — reject as an execution proxy

Pin **katuni4ka/tiny-random-deepseek_v32@38c8fb68c9911ca3e035d80b66421930f4c235c1** only when referring to the fixture. Its primary [manifest](https://huggingface.co/api/models/katuni4ka/tiny-random-deepseek_v32/revision/38c8fb68c9911ca3e035d80b66421930f4c235c1?blobs=true) reports 4,147,620 random parameters and an 8,305,696-byte safetensors file with LFS SHA-256 `4fcfa230a056cd38141645b3ac3cff784d610bf63f8ee98528d38dc4bf0760ae`. It is a community fixture, not an official DeepSeek checkpoint, has no model card, and has no task-quality authority. It includes an [MIT text file](https://huggingface.co/katuni4ka/tiny-random-deepseek_v32/blob/38c8fb68c9911ca3e035d80b66421930f4c235c1/LICENSE), but no matching license metadata or provenance statement.

The [configuration](https://huggingface.co/katuni4ka/tiny-random-deepseek_v32/blob/38c8fb68c9911ca3e035d80b66421930f4c235c1/config.json) nominally declares two layers, 16 routed experts with top-8 routing, MLA ranks, a top-32 indexer, and one next-token-prediction layer. The pinned configuration misspells `first_k_dense_replace` as `firts_k_dense_replace`; the remote configuration class therefore keeps its default of three dense layers, so a two-layer model never reaches MoE. The pinned [model implementation](https://huggingface.co/katuni4ka/tiny-random-deepseek_v32/blob/38c8fb68c9911ca3e035d80b66421930f4c235c1/modeling_deepseek_v32.py) also calls an undefined indexer projection, returns one router tensor where two are unpacked, labels sparse attention incomplete, and contains no MTP execution path. These are source-level disqualifiers; no weight download or execution is needed.

The fixture can inform parser fields, expected tensor names, and rough shape-ledger tests after replacing it with a controlled internal fixture. It cannot validate numerical correctness, kernel speed, memory traffic, quality, serving, or cost. The real architecture reference remains the official [DeepSeek-V3.2 configuration](https://huggingface.co/deepseek-ai/DeepSeek-V3.2/blob/a7e62ac04ecb2c0a54d736dc46601c5606cf10a6/config.json), not this random checkpoint.

### Idiap Gated DeltaNet + NSA 1.4B — trained sparse alternative

Pin **Idiap/gated-deltanet-nsa-1.4B-30B@db8866faafa86b49fcb7e0c9e8f193d9d9d1f89e**. The institutional [manifest](https://huggingface.co/api/models/Idiap/gated-deltanet-nsa-1.4B-30B/revision/db8866faafa86b49fcb7e0c9e8f193d9d9d1f89e?blobs=true) reports 1,323,308,224 F32 parameters in two safetensors shards totaling 5,293,269,848 bytes. The [configuration](https://huggingface.co/Idiap/gated-deltanet-nsa-1.4B-30B/blob/db8866faafa86b49fcb7e0c9e8f193d9d9d1f89e/config.json) has 24 layers, hidden size 2,048, and 12 NSA layers with a 512-token window, 64-token blocks, and 16 selected blocks. The repository has an explicit [MIT license](https://huggingface.co/Idiap/gated-deltanet-nsa-1.4B-30B/blob/db8866faafa86b49fcb7e0c9e8f193d9d9d1f89e/LICENSE.txt).

The [model card](https://huggingface.co/Idiap/gated-deltanet-nsa-1.4B-30B/blob/db8866faafa86b49fcb7e0c9e8f193d9d9d1f89e/README.md) identifies a 1.4B model trained on 30B tokens, requires flash-linear-attention, and demonstrates only CUDA loading. Its training bullet accidentally names a different 0.4B/10B run and its performance section defers vaguely to the paper, so task authority is weaker than NOSA. It can compare a second trained sparse/recurrent memory design on one GPU. It does not implement explicit KV offload, routed MoE, MLA, GLM DSA/index sharing, or MTP.

## Promotion and kill criteria

These are decision rules, not claims about current results. Failure kills the stated proxy or lever; it does not by itself kill every co-design approach.

1. **Identity gate.** A run is inadmissible unless repository revision, weight byte count, and weight SHA-256 match the pins above. Remote code and compiled dependencies must also be revision-pinned.
2. **Mechanism gate.** If the hypothesis requires a structural feature scored 0, kill that proxy for the hypothesis. A score of 1 permits only interface or directional mechanism work, never a GLM transfer claim. The tiny-random fixture is already killed for all numerical, performance, quality, and cost claims.
3. **Minimum Qwen quality gate.** Kill a model-edit candidate if any held-out 4,096-target WikiText boundary exceeds: NLL increase 0.15, perplexity ratio 1.15, logit RMSE 0.50, cosine below 0.98, or top-1 agreement below 0.80. For task promotion, require the lower end of a paired 95% PIQA accuracy-delta interval to be at least −0.02; a passing point estimate alone is insufficient. The existing 256-item result has a lower bound of −0.0234375 and therefore does not meet this confirmatory rule.
4. **Local timing gate.** No Qwen throughput or simulator-calibration claim is admissible until 20 matched baseline/candidate pairs complete. Each run requires three consecutive clean host samples, five seconds apart, with no external process above 20% CPU. The existing campaign completed only one accepted pair and is blocked, so current Qwen evidence is functional and quality-bearing, not stable cost evidence.
5. **NOSA admission gate.** Do not acquire the checkpoint until the pinned Triton, InfLLM-v2, and NOSI stack builds on the intended single GPU. Then require a deterministic sparse decode with fewer selected than eligible blocks, measured host↔device bytes, and the matched 1B FullAttn control. If the control cannot be obtained or reproduced, kill NOSA for causal model-change savings and retain it only for system-mechanics work.
6. **Materiality gate.** Promote a single-GPU lever only if the upper end of its paired 95% cost-ratio interval is at most 0.80 versus the matched tuned control at equal quality and SLO, in both a cache-resident band and an offload-active long-context band. Count accelerator amortization, energy, host memory, and transfer cost. Otherwise kill that lever as commercially immaterial, even if a kernel microbenchmark is faster.
7. **Transfer gate.** Passing every small-model gate promotes a GLM-family experiment; it never approves one. A GLM claim requires the pinned GLM architecture, real expert-routing and DSA/MTP traces, target hardware measurements, tuned vLLM/SGLang controls, and the intended agent workload.

## Practical sequence

Continue local work with Qwen3-0.6B and label every result by the mechanisms it actually exercises. Treat the tiny DeepSeek fixture as rejected source evidence, not a model dependency. On access to one suitable CUDA GPU, qualify NOSA-1B first and Idiap NSA second; use the latter to detect conclusions that are specific to NOSA rather than sparse-memory designs generally. If NOSA cannot cross its runtime, matched-control, quality, and 20% cost gates, the offload branch is de-risked negatively before any custom-hardware commitment.
