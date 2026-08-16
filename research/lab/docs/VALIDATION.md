# Comparative validation

The system exists to determine whether vertical co-design materially lowers inference cost. Absolute simulator accuracy is insufficient; the simulator must predict intervention deltas and candidate ordering.

## Baselines

Every conclusion compares against a frozen but regularly refreshed provider-grade baseline:

- Current vLLM with tuned scheduling and supported quantization.
- Current SGLang.
- TensorRT-LLM where the target hardware supports it.
- Public provider price and latency when the identical model is available.

The report records exact versions, commands, hardware, workload, precision, and dates.

Measured-serving imports accept only measured-hardware provenance and require the exact model, checkpoint, tokenizer, engine build, topology, and canonical trace identity. Failed requests remain in compliance denominators. The importer reports TTFT, TPOT, goodput, and class SLOs but does not invent dollar costs without a separately declared cost source.

## Controlled experiments

The primary analysis is a factorial ablation across five axes:

1. Model representation or architecture.
2. Kernel, layout, and mapping.
3. Serving policy.
4. Hardware architecture.
5. Cross-layer interactions.

Each axis is first changed independently. Combined candidates are then compared against the sum of independent gains so interaction benefits and regressions remain visible.

## Required metrics

- Quality delta against the unchanged checkpoint.
- Input and output tokens that meet the latency SLO.
- TTFT and TPOT distributions.
- Peak and resident memory.
- Component and wall energy.
- Levelized input and output cost per million tokens.
- Minimum sustainable prices at the configured gross margin.
- Prediction error and uncertainty by simulator layer.

## Materiality gates

A small-proxy mechanism needs at least 20% paired cost reduction to justify a larger-model experiment. Joint commodity co-design requires at least 30% lower output cost and 20% lower input cost on two model families. The provider-launch proof requires at least a 1.5x measured fully loaded cost reduction against the best tuned software baseline, and a second model must retain at least a 1.5x gain before claiming a repeatable platform. A custom-hardware program later requires at least a 4x launch-date advantage in the base case and 2x under pessimistic cost, utilization, performance, yield, and incumbent-improvement assumptions.

## Current measured evidence

- Blanket Qwen3-0.6B symmetric groupwise INT4 fails at least one declared numerical gate at every tested group size.
- Selective group-8 INT4 on `o_proj`, `gate_proj`, and `up_proj` passes the frozen 512- and 4,096-target teacher-forced proxies. Exact-source PIQA-256 is 174/256 baseline versus 175/256 candidate, but its paired 95% interval crosses the two-point non-inferiority margin.
- Exact packed tensors retain 37.5% of source BF16 storage, yet the scalar implementation is 1.368× slower and the matched B1/B4/B16/B64 frontier remains 1.7–6.6% slower. These controls are neither tuned BF16 nor serving baselines.
- A prospectively locked explicit AArch64-NEON path measures 4.457× over scalar packed and 3.284× over scalar f32-QDQ on the same tensors with all correctness gates passing. The predicted 1.75× direction is correct, but 44.7% relative effect error fails the 15% predictive-accuracy threshold. The component result does not transfer to a tuned BF16/full-model/serving baseline.
- The largest one-shot KV-sharing change that passes the 4,096-target proxy removes only 1.786% of semantic KV bytes. Full 8→4 sharing destroys quality, and a separate 2,048-target recovery run restores only 3.80% of the NLL gap.
- Local vLLM CPU execution is functional but not repeatable enough for calibration. A frozen campaign accepted one earlier c8 pair and then found no clean host-admission streak in 355 samples, so it launched zero resumed runs.

External simulators are evidence only within their checked boundaries. SCALE-Sim provides uncalibrated native dense-array cycles and finds identical Qwen/GLM architecture ranking in the tested slice. Timeloop's frontend parses the exact problem but its native mapper is blocked. Ramulator2 fully drains and replays synthetic HBM3 traces, but the experiment is patched-native, single-channel, uncalibrated sensitivity rather than GLM or GPU performance.

## Predictive-validity status

The checked [predictive gate](../validation/results/simulator-predictive-validity-gate-2026-07-12.json) inventories 61 JSON artifacts across ten candidate audit families and admits one exact prospective pair. Direction is correct but 44.7% magnitude error exceeds the 15% limit; the remaining intervention, regime, regression, ranking, quality, and SLO requirements also fail. Status is **`NOT_MET`**. No current simulator output may calibrate cost, promote a model-specific co-design advantage, or support provider or silicon decisions.

Promotion requires at least three blinded, precommitted interventions over two context regimes, all directions correct including one predicted regression, relative effect error at most 15%, Spearman rank correlation at least 0.8, globally disjoint calibration and holdout cases, exact artifact identities, and exact quality/SLO evidence for cost. The evaluator verifies real workspace paths, bytes, and in-file content identities; invented hash labels are inadmissible.
