# Local small-model quality validation

This harness measures how symmetric groupwise weight-only INT4 quantize-dequantize changes teacher-forced outputs from a local Qwen3-0.6B checkpoint. It reports NLL, perplexity, full-logit RMSE and cosine similarity, and top-1 token agreement on a deterministic hand-authored agent-style calibration corpus.

The default runner loads the unchanged checkpoint first, records reference logits, unloads it, then loads a separate candidate model and applies INT4 QDQ to eligible `Linear` weights. The memory-bounded expanded run instead keeps both BF16 models resident and evaluates one baseline/candidate window pair at a time without accumulating logits across windows. `lm_head` is excluded by the checked-in configuration. In both modes the candidate stores dequantized floating-point weights, so the Python run measures the numerical quality mechanism only. Separate Rust artifacts now measure three packed tensors and local scalar/batch kernels; they do not make the Python quality run runtime-compressed or establish full-model memory, latency, energy, or cost.

The result is evidence for Qwen3-0.6B only. It cannot validate Qwen3-8B, KV-cache precision, reduced KV heads, FFN changes, serving behavior, or custom hardware.

Run the unit tests from the repository root:

```sh
source /Users/js/dev/vllm-study/.venv/bin/activate
python -m unittest discover -s validation/tests -v
```

Run the offline validation after placing the complete local checkpoint under `models/Qwen3-0.6B`:

```sh
source /Users/js/dev/vllm-study/.venv/bin/activate
python -m validation.qwen_int4_quality \
  --model models/Qwen3-0.6B \
  --config validation/config/qwen3-0.6b-int4-quality-v1.json \
  --corpus validation/corpora/agentic-calibration-v1.json \
  --output artifacts/qwen3-0.6b/int4-quality-v1.json
```

The harness uses local-only Transformers loading and exits with an explicit error before model loading when `config.json` or checkpoint weights are missing. The output contains hashes for the configuration, corpus, model configuration, and every weight file, plus exact software and machine provenance. The pass/fail gate is a declared calibration threshold, not a substitute for downstream task benchmarks.

## Measured INT4 sweep

The first measured sweep used the exact Qwen3-0.6B weight file with SHA-256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`. Symmetric round-to-nearest INT4 was evaluated at group sizes 8, 16, 32, 64, and 128. None passed every declared numerical gate.

| Group size | Effective bits / quantized weight | NLL delta | Perplexity ratio | Logit RMSE | Logit cosine | Top-1 agreement | Pass |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 | 6.000 | -0.0314 | 0.9690 | 0.7507 | 0.9749 | 0.8903 | No |
| 16 | 5.000 | +0.0070 | 1.0070 | 0.8841 | 0.9649 | 0.8194 | No |
| 32 | 4.500 | +0.0415 | 1.0424 | 0.9891 | 0.9561 | 0.8000 | No |
| 64 | 4.250 | +0.1329 | 1.1422 | 1.1675 | 0.9381 | 0.7290 | No |
| 128 | 4.125 | +0.2088 | 1.2322 | 1.2728 | 0.9259 | 0.7419 | No |

The compact provenance-bearing result is checked in as [`results/qwen3-0.6b-int4-sweep-v1.json`](results/qwen3-0.6b-int4-sweep-v1.json). Group size 8 passed the NLL, perplexity, and top-1 thresholds but missed the logit RMSE and cosine thresholds, while its scale metadata raises effective storage to six bits per quantized weight. The next model-side experiments are calibration-aware or rotation-aware INT4 and task-level evaluation; the analytical Qwen3-8B W4 saving remains unvalidated.

## Measured selective INT4 replication

The previously selected group-8 candidate quantizes each layer's `o_proj`, `gate_proj`, and `up_proj` weights while retaining Q/K/V, `down_proj`, and `lm_head` at BF16. It passed all five declared teacher-forced proxy gates on the 155-target selection corpus, an independently sourced 512-target WikiText-2 subset, and a larger sequential 4,096-target WikiText-2 test subset.

The larger checked result is [`results/qwen3-0.6b-int4-o-gate-up-wikitext2-sequential4096-bf16-v1.json`](results/qwen3-0.6b-int4-o-gate-up-wikitext2-sequential4096-bf16-v1.json). It covers contiguous token positions 32 through 4,127 of a pinned 299,078-token test stream, partitioned into 64 non-overlapping targets with rolling 32-token contexts. Neither this corpus nor its result was used to select the tensor mask.

| Metric | 4,096-target result | Gate | Outcome |
| --- | ---: | ---: | --- |
| Mean NLL delta | +0.06184 | ≤ +0.15 | Pass |
| Perplexity ratio | 1.06379 | ≤ 1.15 | Pass |
| Logit RMSE | 0.46070 | ≤ 0.50 | Pass |
| Logit cosine | 0.98995 | ≥ 0.98 | Pass |
| Top-1 agreement | 86.13% | ≥ 80% | Pass |

This is a teacher-forced BF16 QDQ quality proxy, not task, runtime, or cost proof. The candidate used BF16 model parameters, float32 quantization arithmetic and metric accumulation, and dequantized BF16 weights at execution time. It did not materialize packed INT4 storage or a packed kernel. The 24.6289% mixed-precision weight-byte reduction remains an arithmetic estimate; throughput, latency, energy, serving behavior, task success, and dollars per token remain unmeasured. The 4,096 targets are also only the first part of the pinned stream, not canonical full-test WikiText-2 perplexity, and the result does not transfer to Qwen3-8B or GLM-5.2.

## Packed INT4 kernel controls

The Rust [`packed-kernel smoke`](../experiments/qwen3-0.6b/int4-packed-kernel-smoke-v1.json) stores exact layer-zero `o_proj`, gate, and up tensors as signed group-8 nibbles plus BF16 scales. It retains 37.5% of source BF16 bytes and matches an independent packed-format QDQ control exactly, but its simple scalar loop is 1.368× slower.

The corrected [`matched batch frontier`](../experiments/qwen3-0.6b/int4-packed-batch-frontier-v1.json) uses identical group/pair/lane traversal for packed and independently materialized f32-QDQ weights at B=1, 4, 16, and 64. All work counts and outputs match exactly. Packed remains 6.60%, 1.73%, 3.05%, and 2.04% slower, so there is no observed crossover. Neither artifact uses a tuned BF16/BLAS/vLLM control, explicit SIMD, a full model, or measured energy. Their BF16 stored scales also differ from the earlier float32-scale quality transform; the frozen task-quality bridge must pass before the packed representation inherits any quality evidence.

The prospective [`AArch64 NEON result`](../experiments/qwen3-0.6b/int4-aarch64-neon-v1.json) reuses the three exact tensors and immutable BF16-scale representation. With preallocated outputs and 31 alternating-order release samples, summed medians are 1.063583 ms NEON, 4.740666 ms scalar packed, and 3.493126 ms scalar f32-QDQ. The explicit path is therefore 4.457× and 3.284× faster than those local scalar controls; all work and correctness gates pass with 5.25e−6 maximum error. Its [prediction](predictions/qwen3-0.6b-int4-aarch64-neon-v1.json) was committed before measurement at 1.75×. Direction is correct, but the 44.7% relative effect-size error fails the 15% predictive threshold. This remains a one-thread batch-one component result, not tuned BF16/Accelerate, full model, quality transfer, serving, energy, or cost.

The BF16-scale bridge now passes the same five teacher-forced gates at both held-out sizes. The [`512-target result`](results/qwen3-0.6b-int4-o-gate-up-bf16scale-wikitext2-test-v1.json) reports NLL delta +0.03160, perplexity ratio 1.03210, RMSE 0.46980, cosine 0.98993, and top-1 agreement 87.70%. The [`4,096-target result`](results/qwen3-0.6b-int4-o-gate-up-bf16scale-wikitext2-sequential4096-v1.json) reports +0.05935, 1.06115, 0.46078, 0.98995, and 86.25%. Both execute materialized BF16 weights, not packed kernels.

The first PIQA subset artifact was withdrawn because its loader did not preserve exact source trailing whitespace in 30 of 512 choices. The corrected [`exact-source PIQA-256 result`](results/qwen3-0.6b-int4-o-gate-up-piqa256-bf16scale-v1.json) keeps the frozen indices, mask, seed, prompt, scoring rule, and two-point gate. Baseline accuracy is 174/256 (67.97%) and candidate accuracy is 175/256 (68.36%), so the point gate passes. The paired-bootstrap 95% delta interval is [−2.34,+3.13] points and crosses the −2-point margin, making confirmatory non-inferiority inconclusive. It is not a full benchmark, decontamination, packed-kernel-equivalence, agent-quality, safety, serving, energy, or cost result.

## Controlled vLLM CPU repeatability campaign

The additive `validation.qwen_vllm_repeatability` harness freezes 20 deterministically shuffled cold/warm pairs across c1/c2/c4/c8, captures host and software provenance, binds execution to performance cores, retains contamination aborts, and requires unrelated processes to stay below 20% CPU. It does not relax the threshold to manufacture a result.

The checked [`terminal result`](results/qwen3-0.6b-vllm-cpu-repeatability-v1.json) accepted one earlier c8 cold/warm pair but could not admit the resumed campaign. A preflight gate sampled the host every five seconds and required three consecutive clean samples. All 355 samples over 1,802.79 seconds failed to form a streak; the final blocker was `mds_stores` at 315.5% CPU. The terminal is `host_contamination_blocked`, not a performance measurement. Only 2/40 planned runs exist, so repeatability, simulator calibration, GPU/provider performance, energy, and cost claims remain false.

## Cross-stack predictive and hardware gates

The checked [`simulator-predictive-validity-gate-2026-07-12.json`](results/simulator-predictive-validity-gate-2026-07-12.json) inventories 61 JSON artifacts across ten candidate audit families and admits one exact prospective prediction/measurement pair. Its direction is correct, but 44.7% relative effect error fails the 15% bound; intervention/regime counts, regression coverage, rank correlation, and exact quality/SLO evidence are also insufficient. Status remains `NOT_MET`. The evaluator verifies safe workspace-relative paths, actual file SHA-256 values, in-file scope/value/content identities, disjoint calibration/holdout cases, and exact quality/SLO bindings. No current simulation is calibrated for cost or provider claims.

The patched-native [`qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json`](results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json) executes 18 synthetic HBM3 cases twice and drains all 1,363,968 callbacks. Sorting the same selected logical-token set lowers cycles 27.744% in a one-32-byte-line geometry but raises them 59.194% when each token expands to a synthetic 1,152-byte BF16 record. This is a within-geometry locality/bank-parallelism sensitivity result, not a physical-address sort, real GLM trace, GPU latency, calibration, energy, quality, or cost result.

The [`inference-codesign competitive landscape`](results/inference-codesign-competitive-simulation-landscape-2026-07-12.json) binds 30 primary sources and 19 entries across 12 occupied layers. It records the public baseline the research program must beat; it does not reproduce competitor performance or prove a commercial moat.

## Tensor-derived KV-head sharing frontier

The additive `validation.qwen_kv_dedup_quality` harness tests an exact architecture/runtime opportunity rather than a quantization proxy. It finds a minimum joint K/V-weight-distance head pairing independently in each Qwen layer, replaces selected pairs by their BF16 mean, and emits the alias mapping a future attention kernel would require. The standard Transformers execution intentionally keeps the original eight-head tensor shape, so the quality result is measured but the KV-cache and checkpoint reductions are analytical. Both runtime-reduction flags remain false.

The checked [`results/qwen3-0.6b-kv-head-dedup-quality-frontier-v1.json`](results/qwen3-0.6b-kv-head-dedup-quality-frontier-v1.json) contains nine 512-target points. One pair in each of four tensor-selected layers is the largest passing point: 1.7857% estimated KV-byte reduction and 0.1759% estimated weight-byte reduction. Five layers fails RMSE and cosine. Full four-pair sharing across all 28 layers estimates 50% lower KV bytes but fails catastrophically.

The maximum frontier pass was then rerun over 4,096 held-out targets in [`results/qwen3-0.6b-kv-head-pair-mean-layer4-wikitext2-sequential4096-bf16-v1.json`](results/qwen3-0.6b-kv-head-pair-mean-layer4-wikitext2-sequential4096-bf16-v1.json): NLL delta +0.001409, perplexity ratio 1.001410, logit RMSE 0.438812, cosine 0.990930, and top-1 agreement 87.646%. All five gates pass. Its impossible cache-only, zero-overhead speedup ceiling is just 1.0182×. The result rejects one-shot head merging as a material lever; it does not reject trained GQA conversion. Primary recovery evidence and the separate-data experiment contract are recorded in [`results/qwen-kv-head-reduction-literature-2026-07-12.json`](results/qwen-kv-head-reduction-literature-2026-07-12.json).

The executed recovery result is [`results/qwen3-0.6b-kv-head-recovery-2k-v1.json`](results/qwen3-0.6b-kv-head-recovery-2k-v1.json). Exact full 8→4 pair sharing with frozen K/V and 1,376,256 rank-8 Q/O adapter parameters recovered only 3.80% of the initial NLL gap after 2,048 separate train targets. On the fixed 512-target holdout, perplexity remained 2,534.8× baseline, RMSE was 4.415, cosine 0.3516, and top-1 agreement 1.37%; all gates failed. The projected 8,192-target continuation was stopped. This rejects that exact small-budget recipe while leaving materially different conversion methods open.

Run a quality point with:

```sh
source /Users/js/dev/vllm-study/.venv/bin/activate
python -m validation.qwen_kv_dedup_quality \
  --model models/Qwen3-0.6B \
  --config validation/config/qwen3-0.6b-kv-head-pair-mean-layer4-wikitext2-sequential4096-bf16-v1.json \
  --corpus artifacts/qwen3-0.6b/corpora/wikitext-2-test-sequential-4096-v1.json \
  --output artifacts/qwen3-0.6b/kv-head-pair-mean-layer4-wikitext2-sequential4096-bf16-v1.json
```

## Measured vLLM CPU throughput

The local CPU build of vLLM revision `bec0a4ede621bc9f1ec7be39b79ed2e286da4ca1` successfully ran the exact Qwen3-0.6B checkpoint on an Apple M4 Pro. Eight offline requests with 128 input and 32 output tokens each completed in 20.7714 seconds: 0.3851 requests/s, 49.2986 input tokens/s, 12.3246 output tokens/s, and 61.6232 total tokens/s.

The compact record is [`results/qwen3-0.6b-vllm-cpu-throughput-v1.json`](results/qwen3-0.6b-vllm-cpu-throughput-v1.json). It is a real software-path measurement, but the offline benchmark does not expose per-request first-token timestamps and therefore does not satisfy the measured-serving contract. It cannot calibrate Qwen3-8B, H100, provider economics, or custom hardware.

## Public-market and incumbent-stack snapshots

The checked [`SCALE-Sim v3 Qwen/GLM sweep`](results/qwen3-glm-scalesim-v3-gemm-sweep-v1.json) is the first native external hardware-oracle result. Twelve cases cover exact Qwen `o_proj` and GLM expert-gate GEMMs across six array/dataflow/SRAM configurations. Output-stationary 32×32 minimizes cycles for both; their base rankings are identical, and 4 MiB SRAM does not reduce native filter reads or core cycles. The result permits pinned same-oracle cycle/access comparisons only, not BF16/NVFP4 arithmetic, GPU latency, energy, area, whole-model execution, serving, or cost.

[`results/provider-economics-2026-07-12.json`](results/provider-economics-2026-07-12.json) captures public provider prices, dedicated accelerator rates, source identities, and the explicit synthetic agent-mix break-even case. [`results/glm-5.2-incumbent-stack-2026-07-12.json`](results/glm-5.2-incumbent-stack-2026-07-12.json) captures the disclosed Baseten, Fireworks, and NVIDIA GLM-5.2 optimization stacks and their evidence boundaries.

These snapshots contain public facts, vendor-reported measurements, and derived arithmetic. They are not local measurements and do not reveal provider aggregate capacity, COGS, utilization, errors, contract prices, or margin. In particular, Fireworks' 446 token/s peak and Baseten's 280+ token/s report are per-user streaming metrics, not billable fleet throughput. They may define an SLO control only after the exact benchmark workload is reproduced; they cannot calibrate the economic engine directly.
