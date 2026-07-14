# Sol context handoff

This file is the durable reset point for the model-specific inference co-design research. It records what is measured, what is modeled, why Sol and Fable/Sartor reached different business conclusions, and what must happen next.

## GLM-4.7-Flash update — 2026-07-14

The Nebius campaign decision is `CONTINUE_NARROWLY`; the source-pinned eight-KV-split MLA lineage is `STOP`. An exact-shape L40S microbenchmark measured a 40.27% aggregate full grouped-attention reduction, but a retained same-session A/B/A/B/A server sequence measured only +1.0476% and +1.0447% drift-corrected c8 throughput effects against a 5% gate. Traces prove the candidate ran: summed c8 attention/MLA work fell 33.43% and all summed decode kernel work fell 14.09%, while vLLM decode annotation span changed +0.38%. The component win is therefore overlapped or off the current critical path; dense GEMM/GEMV is the largest residual measured family.

All five final arms passed semantic, exact geometry, SLO, cache, paired diagnostic, artifact, and cleanup gates, but the absolute compact quality point screen remains failed and showed exact-output instability across identical stock arms. No general quality-adjusted, Fireworks/Baseten, settled-cost, or custom co-design advantage is admitted. Final session cleanup verified instance GET not-found and zero instances/disks. Conservative Nebius spend is `$17.656500383/$25`, leaving `$7.343499617`.

Canonical decision: `experiments/glm47flash/campaign_100/DECISION_CONTINUE_NARROWLY_SPLIT8_STOP_2026-07-14.json`, SHA-256 `e51b5324a7c2c28dc66122f1f5776bb898fd0573106d51311da89edf3c031131`. Resume by calibrating a prospective expanded quality suite off GPU, then measuring a matched profiler-off/on phase trace with Nsight Systems, available standard DCGM fields, host/scheduler timing, attribution coverage, and explicit missing counters. Do not test another MLA split/tile variant on this workload without new critical-path evidence.

## Repository and history

- Canonical path: `/Users/js/dev/gradiated/research/sol`
- Sibling lineage: `research/fable` is the Sartor workstream.
- Remote: `origin/main` is the canonical published branch.
- Current main tip: `19219924d55ae30499193d0894d7fd09fa8f3d0d`.
- All 39 commits reachable from main use `Joshua Snyder <joshua@timenavi.com>` as both author and committer.
- The pre-email-rewrite tip is retained only as the local ref `refs/backup/gradiated-main-pre-timenavi`.
- The live Fable bridge status file can change while the bridge runs. Its unstaged timestamp update is runtime state, not research evidence.

## Sol conclusion

Sol is the fail-closed evidence and simulation line. Its current business verdict is:

> Continue model/kernel/simulator research; do not claim a measured $/token reduction, provider advantage, calibrated full-E2E simulation, 5–10× result, buildable custom hardware, or tapeout case.

The strongest positive result is a prospective local Qwen3-0.6B AArch64 NEON packed-INT4 component experiment. The prediction was locked before measurement at 1.75× versus the scalar packed control. The holdout measured 4.457× versus scalar packed and 3.284× versus scalar f32-QDQ over three exact tensors, with correctness, work, and allocation checks passing. The measured time reduction was 77.565% versus a predicted 42.857%, a 44.7% relative effect error, so the direction was right but the predictor failed its declared ≤15% magnitude gate. This is one-thread, batch-one, layer-zero component evidence, not a full model, tuned BLAS, vLLM, serving, quality, energy, or cost result.

Other binding Sol evidence:

- Selective Qwen INT4 passes narrow teacher-forced numerical gates and a frozen PIQA-256 point gate, but its paired interval is inconclusive and its scalar/matched batch kernels regress against their controls.
- The largest one-shot Qwen KV-sharing change that passes both proxy quality gates saves only 1.786% of KV bytes; full 8-to-4 sharing fails catastrophically. A rank-8 Q/O recovery run restores only 3.80% of the NLL gap.
- The vLLM CPU repeatability campaign is host-contamination blocked; there is no accepted repeated serving calibration.
- A fully drained synthetic Ramulator2 sweep reverses logical-token sorting from 27.744% better for a 32-byte probe to 59.194% worse for a 1,152-byte BF16 record. Geometry-insensitive locality is rejected.
- The GLM-5.2 mapping screen is exact token-geometry arithmetic. Residency preference changes with context and concurrency, but candidate full capacity is uncertain for all tested requests.
- The competitive dossier finds generic full-stack simulation, deployment search, obvious DSA/index/gather mechanisms, and standard serving optimization already occupied. The surviving wedge is validated non-obvious model-to-hardware discovery.

Machine-readable anchors:

- Business ledger: `validation/results/model-stack-business-decision-2026-07-12.json` — 31 sources, 100 fact checks, 30 arithmetic checks, 20 decisions; all business promotions remain false.
- Predictive gate: `validation/results/simulator-predictive-validity-gate-2026-07-12.json` — 61 artifacts, 10 candidate audit families, one admitted pair, `NOT_MET`.
- NEON measurement: `experiments/qwen3-0.6b/int4-aarch64-neon-v1.json`.
- NEON prediction: `validation/predictions/qwen3-0.6b-int4-aarch64-neon-v1.json`.
- Full decision brief: `docs/WAKEUP_BRIEF_2026-07-12.md`.

## What Fable/Sartor concluded

Fable’s living report is a different evidence product with a broader and more optimistic claim policy. Its current headline is a **3.94× Monte Carlo co-design median**, `[P10 2.93, P90 5.04]`, with `P(≥3×)=88%`. Its GLM-5.2 study reports a modeled baseline of `$0.709/Mtok`, cumulative software/model levers reaching `$0.264/Mtok` (2.7×), and an illustrative family ASIC reaching `$0.104/Mtok` (6.8× cumulative). Fable explicitly labels the ASIC tier speculative and lists missing H100/H200 measurements, EP imbalance, prefill sharding, and surgery quality as gaps.

Fable also has valuable measured foundations:

- Barge versus its vLLM CPU comparison reports 525 versus 246 output tok/s, or 2.1×, on the M4. The report itself notes that the comparison is macOS ARM, f32 Barge versus bf16 vLLM, and that the vLLM backend is not a tuned CUDA incumbent.
- A real SmolLM2 head-pruning surgery plus healing measures 1.051× engine throughput, 1,308 versus 1,244 tok/s. The matched finetuning control improves the unpruned model more than the pruned model, so the honest quality cost is +8.7% perplexity versus control; instruct sanity fails after raw WikiText healing.
- All-layer int8 KV is nearly lossless in its local perplexity protocol (+0.06%); blanket int4 KV is not (+26%).
- CLA/KV sharing is learnable but not recovered to parity: the healed result is still 43.7% worse perplexity than the base model and 63% worse than the matched control.
- The calibrated roofline uses a 0.73 realization factor from a public GB200 anchor and a 0.53 inferred duty factor from a DeepSeek disclosure. There is no direct H100/H200 money run in that report.

## Why the conclusions differ

The disagreement is mostly denominator and evidence-policy disagreement, not a contradiction in the local observations.

1. **Fable asks whether a plausible co-design portfolio could be economically large under calibrated assumptions.** It compounds cache, precision, serving, model, kernel, hardware, utilization, and margin scenarios, then Monte Carlo-samples lever survival. Its 3.94× and 6.8× values are scenario/posterior outputs, not one same-trace measured cost comparisons.
2. **Sol asks whether an economic claim is already unlocked by exact, scope-matched evidence.** It refuses to multiply marginal effects across models, workloads, controls, or evidence classes. Its `NOT_MET` result is therefore a claim gate, not a statement that every Fable mechanism is false.
3. **The local benchmark denominators differ.** Fable’s Barge result is useful evidence that a deliberately narrow Rust engine can beat an untuned macOS vLLM path. Sol’s NEON result compares exact kernel controls and then refuses to extrapolate that component win to a tuned full serving stack.
4. **Model interventions differ.** Fable’s positive head-pruning loop includes real weights, healing, a matched control, and a measured engine run, but it also exposes domain-adaptation and instruct-quality costs. Sol’s Qwen experiments select different tensors and directly reject the tested KV-sharing recipes. Both are model-specific results; neither transfers automatically to GLM-5.2.
5. **The ASIC tier is the largest divergence.** Fable’s family-ASIC is a structured counterfactual with explicit BOM, bandwidth, utilization, and NRE assumptions. Sol treats that as a useful design hypothesis but not buildability or cost evidence until the full checkpoint traffic, quality, SLO, PPA, package, yield, and volume contract are measured.

## Which conclusion is more accurate?

For **research prioritization**, Fable is more informative: it has a wider model/surgery loop, useful local measurements, and a calibrated scenario engine that identifies where a 3–5× opportunity might come from.

For **an investor or go/no-go claim today**, Sol is more accurate. The Fable 3.94× number should be described as a model-conditioned scenario posterior; the 6.8× GLM result should be described as a cumulative modeled study with an illustrative ASIC tier. Neither is a measured fully loaded $/token comparison against an incumbent-grade GLM deployment. The defensible combined statement is:

> Fable demonstrates that large gains are plausible under explicit assumptions and has closed several local mechanism loops. Sol demonstrates that those gains are not yet calibrated, composable, or commercially proven. The opportunity remains worth testing, but the company case is not yet established.

Do not collapse either line into “Sartor was wrong” or “Sol disproved co-design.” The correct reconciliation is **hypothesis generation versus claim admission**.

## Next decisive experiments

1. Run one exact incumbent-versus-candidate comparison on the same frozen agent trace, with quality, TTFT/TPOT/E2E SLOs, throughput, power, failures, availability, and fully loaded cost.
2. Retest the NEON packed path against tuned Accelerate/BLAS and a full packed model, not only scalar Rust controls. Lock the next prediction before timing.
3. Re-run Fable’s head-prune and int8-KV findings under the Sol artifact contract: exact model revision, exact workload, matched control, quality suite, serving SLOs, and cost denominator.
4. Build a three-intervention, two-regime predictive campaign including a predicted regression. Require ≤15% effect error and rank correlation before allowing simulator outputs into economics.
5. For GLM-5.2, use the native checkpoint geometry and public agentic trace only to select measurements. Do not transfer Qwen or SmolLM2 performance without a fresh GLM experiment.
6. Keep custom silicon in the conditional stage until a surviving software/model change retains a material advantage against the best commodity implementation and supports contracted volume.

## Reset commands

From the canonical tree:

```sh
cd /Users/js/dev/gradiated/research/sol
cargo test --workspace
source /Users/js/dev/vllm-study/.venv/bin/activate
python -m unittest discover -s validation -p 'test_*.py' -t .
```

The full durable reports are `docs/WAKEUP_BRIEF_2026-07-12.md`, `docs/OVERNIGHT_REPORT_2026-07-12.md`, `docs/BUSINESS_VALIDATION.md`, and this file. `research/fable/docs/REPORT.md` is the corresponding Sartor/Fable living report.
