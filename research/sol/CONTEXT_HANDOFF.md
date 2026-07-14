# Sol context handoff

This file is the durable reset point for the model-specific inference co-design research. It records what is measured, what is modeled, why Sol and Fable/Sartor reached different business conclusions, and what must happen next.

## GLM-4.7-Flash update — 2026-07-14

The Nebius campaign decision is `CONTINUE_NARROWLY`; the source-pinned eight-KV-split MLA lineage is `STOP`. An exact-shape L40S microbenchmark measured a 40.27% aggregate full grouped-attention reduction, but a retained same-session A/B/A/B/A server sequence measured only +1.0476% and +1.0447% drift-corrected c8 throughput effects against a 5% gate. Traces prove the candidate ran: summed c8 attention/MLA work fell 33.43% and all summed decode kernel work fell 14.09%, while vLLM decode annotation span changed +0.38%. The component win is therefore overlapped or off the current critical path; dense GEMM/GEMV is the largest residual measured family.

All five final split-8 arms passed semantic, exact geometry, SLO, cache, paired diagnostic, artifact, and cleanup gates, but the absolute compact quality point screen remains failed and showed exact-output instability across identical stock arms. No general quality-adjusted, Fireworks/Baseten, settled-cost, or custom co-design advantage is admitted. The subsequent factory observer allocations are all cleaned and settled. The factory's integer-microdollar ledger now records `$18.277888/$25` settled and `$6.722112` available, excluding public IPv4/egress and pending invoice reconciliation.

Canonical decision: `experiments/glm47flash/campaign_100/DECISION_CONTINUE_NARROWLY_SPLIT8_STOP_2026-07-14.json`, SHA-256 `e51b5324a7c2c28dc66122f1f5776bb898fd0573106d51311da89edf3c031131`. Resume through the shared factory with `PYTHONPATH=research/factory/src python3 -m grad_research bootstrap-glm47 --root "$RESEARCH_LAB_ROOT" --campaign-dir research/sol/experiments/glm47flash/campaign_100`, using a persistent backed-up lab root. The generated coordinator brief preserves the final residual, stopped split-8 lineage, diverse next portfolio, and instrumentation debt. First calibrate the expanded quality suite off GPU, then measure a matched profiler-off/on phase trace with Nsight Systems, available standard DCGM fields, host/scheduler timing, attribution coverage, and explicit missing counters. Do not test another MLA split/tile variant on this workload without new critical-path evidence.

### Observer campaign stop handoff — 2026-07-14

The user explicitly stopped the active campaign. There are no live Nebius instances or disks, no factory reservation, and no unclean allocation. Direct lookup for the last resource returned not-found; fresh provider inventory measured zero instances and zero disks. Immutable observer runs V31–V35 are packed and factory-recorded. Their incremental derived costs were `$0.122393832`, `$0.139942073`, `$0.126219561`, `$0.163587298`, and `$0.069241150`; V35 is classified `user_requested_stop`, not a scientific or preflight failure.

The observer work did close the target-hardware capability path before the stop:

- Nsight Systems `2026.3.1.157` installs from the Ubuntu 22.04 NVIDIA devtools repository only after verifying fingerprint `AE09FE4BBD223A84B2CCFCE3F60F4B3D7FA2AF80`.
- Nsight GPU Metrics is measured unsupported on the Nebius L40S/runtime combination. Keep it explicitly unavailable; retain 100 ms `nvidia-smi` utilization, VRAM, power, clocks, and temperature telemetry.
- CUDA/NVTX/OSRT, node-level CUDA Graph, process-tree sampling/context switches, PyTorch CUDA, and SQLite export all passed on the target L40S after removing the runtime's CUDA-compat `ld.so` entries and running `ldconfig`. The retained V34 repair produced a 539,965-byte `.nsys-rep` and 2,015,232-byte SQLite export.
- V35 was stopped during fresh-host bootstrap before checkpoint transfer. No model inference or observer bracket result exists.

Run V35 remains immutable and must never be reused. Its resume contract was fulfilled by the V36 cycle below with a new controller identity and freshly bound preflight/spec; any later retry must likewise use a new immutable identity. Keep the repaired ten-minute retention policy. The full evidence narrative and bundle hashes are in `experiments/glm47flash/REPORT.md`.

### Observer V36 cycle — 2026-07-14

V36 used new factory identity `glm47-observer-diagnostic-l40s-v6` and preserved the scientific observer contract. It passed the 35-reference deep audit, fresh zero-instance/zero-disk reconciliation, 196 local tests, target Nsight/CUDA preflight, and the verified one-time 20.17 GB transfer. The model endpoint then remained connection-refused for the bounded health window, before any request or scored observer arm. Treat this as operational failure only; the dense-versus-host bottleneck belief is unchanged.

Cleanup and settlement passed at `$0.286961496`; factory bundle `6b69151c9f6ebf59e83a09995e963291106111cb9c802223a7b4667b625ff315` deep-verifies. The factory ledger is `$18.564850/$25` settled and `$6.435150` available, with zero reserved spend and no live Nebius resources. Before another paid run, add fail-closed partial remote packaging for server exit status and logs and audit the V36 launch/health path offline. Use a new immutable identity only after naming a materially changed operational variable; do not change the scientific observer geometry.

### Observer V36 offline recovery cycle — 2026-07-14

The bounded zero-cost audit falsified a readiness-window explanation. V36 emitted exactly 54 connection-refused health attempts and returned well before its 180-by-two-second readiness allowance; successful V24R2–V28R1 model loads took 108–112 seconds. Under the harness logic, the only pre-deadline exit path was loss of the tracked A1 server process. The server return code and per-arm stdout/stderr were not recovered, so the root cause remains operationally unclassified. The always-on observer patch—especially its NVTX wrapper during model initialization or CUDA graph capture—is the leading changed launch variable, but that is an inference, not a result. No dense-device or host/scheduler scientific belief changed.

The remote harness now atomically refreshes a hashed partial archive before and during readiness. It retains server status/exit history, stdout/stderr, per-attempt health events, phases, partial metadata, and an internal content manifest. The controller prefers the verified complete archive, otherwise verifies the partial archive's outer hash and internal manifest, forces `FAIL`, and never scores it. Bash syntax, Python compilation, 19 focused tests, and all 200 campaign tests pass. Factory result `glm47-v36-launch-health-recovery-c1-result` cost `$0.00`; staging manifest SHA-256 is `392867bc666fdc12625b44a208d4356e288ebe04e1e7ff8094f618eea4ee68f0`.

Next: validate the exact patch in the pinned derived image using compilation, imports, and a minimal NVTX invocation. If that passes, only a new immutable operational diagnostic that first proves unpatched stock startup before patched observer startup is admissible. Do not lengthen readiness, modify the science geometry, or spend on an opaque retry.

### Observer patch exact-pin smoke — 2026-07-14

The zero-cost GPU-free compatibility rung passed in a local runtime reconstructed from the exact V36 amd64 base digest and Transformers commit. The pristine scheduler and GPU-runner hashes matched `96f736...16a0` and `e8a73e...f9bb`; Torch `2.9.1+cu129`, vLLM `0.15.0`, and Transformers `5.3.0.dev0` matched V36. Stock imports passed, the exact `ecaa1de6...65c6b` patch applied, both patched modules compiled and imported in fresh processes, the synthetic scheduler event ID matched the runner NVTX label, and `torch.cuda.nvtx.range` entered/exited cleanly with no GPU present.

The first attempt had an operational parser defect because vLLM informational stdout preceded the JSON record. A recorded parser-only amendment selected the final JSON object and reran the unchanged causal smoke; it did not update beliefs. Factory result `glm47-observer-patch-pinned-image-smoke-c1-result` cost `$0.00`; reconstructed image digest is `4672d4aa...f3f62c` and staging manifest is `1576d4f475b010074deacbdcbebed5d5f16f47858a672bb9b7add7aebde3dad2`.

This falsifies source mismatch, syntax, import-time, correlation-identity, and basic host NVTX API explanations. It does not test the deleted V36 final image bytes, driver injection, model initialization, first GPU forward, or CUDA Graph capture. The next paid identity must therefore be an operational startup isolation on one retained L40S: verify/transfer once, prove unpatched stock health, stop it, apply the patch, then start the patched observer path with partial evidence enabled. Preserve the observer A1/B1/A2 science contract, readiness limit, budget, and cleanup deadline. Scientific bottleneck beliefs remain unchanged.

### Observer V37 preparation cycle — 2026-07-14

Immutable run `glm47-observer-diagnostic-l40s-v7` is prepared and factory-valid, but was deliberately not admitted or executed in this bounded cycle. The new excluded `STOCK_STARTUP` stage uses the exact A1 command, checkpoint, runtime, and 180-by-two-second readiness bound with zero requests. It must reach health, then pass a bounded 30-second TERM/KILL fallback and verified process absence before the observer patch can apply. A failure remains operational and is retained in the hashed partial archive; it cannot update scientific beliefs.

The patched A1/B1/A2 geometry, `$0.55` cap, `$0.07` cleanup reserve, 1,760-second science/setup limit, and 2,000-second absolute deadline are unchanged. The candidate harness identity is `60453752...48ef9e`; factory validation content hash is `819ea18f...8534d`; the preparation verification artifact is `cdc53122...69f6a`; and the final 17-file plan manifest is `9550fbff...1508d`. DevEx, diff, shell syntax, Python compilation, and all 204 campaign tests passed. Fresh provider reconciliation measured zero instances and zero disks; no reservation or provider resource was created, so the ledger remains `$18.564850/$25` settled and `$6.435150` available.

Next cycle only: resume with exact owner `supervisor-glm47`, run the deep audit and fresh zero-resource reconciliation, regenerate V37 with a fresh UTC deadline, then admit and immediately execute, clean up, settle, and interpret it. The V36 exit remains localized to target-GPU/final-image/model-initialization behavior, especially first forward or CUDA Graph capture; dense-device versus host/scheduler beliefs are unchanged.

### Observer V37 execution cycle — 2026-07-14

V37 executed under exact owner `supervisor-glm47` after a 52-reference deep audit and fresh zero-instance/zero-disk reconciliation. The target Nsight/CUDA preflight and tiny transfer probe passed, and the verified 20.17 GB checkpoint transferred once. The excluded unpatched `STOCK_STARTUP` reached health and stopped cleanly. The exact observer patch then applied, and patched A1 also reached health and completed. This falsifies the V36 startup failure at both unpatched stock startup and the patched A1 startup path.

B1 did not start: Nsight Systems `2026.3.1.157` rejected `nsys launch --force-overwrite=true` as an unrecognised option. The failure is operational and occurred before B1 server startup. The verified partial archive omitted A1 request/workload/gate/scheduler files, so A1 is not admissible scientific evidence despite completing remotely; no scored bracket, observer comparison, quality result, or dense-device versus host/scheduler belief update exists.

Cleanup verified direct not-found plus zero Nebius instances and disks. The `$0.319441958` session cost is settled; the factory ledger is `$18.884292/$25` settled, `$6.115708` available, and `$0` reserved. Partial archive SHA-256 is `50459d5f...008c`; the deep-verifiable operational-failure bundle is `89bcbafc...27ab`. The next cycle may repair only the operational launch boundary under a new immutable identity: remove the unsupported option and add an exact-version, pre-transfer `nsys launch --help` capability fixture/gate. Preserve the startup isolation, A1/B1/A2 science geometry, budget authority, deadline, partial-evidence contract, and cleanup policy.

### Nebius budget authority amendment — 2026-07-14

The user clarified that `$28.60` is the additional available Nebius balance, not the lifetime ceiling. The factory ledger now records total authority `$48.034292`, `$18.884292` settled, `$0.55` reserved by the active V8 run, and `$28.60` available for new admissions. This is an accounting amendment only; historical decision artifacts remain bound to their original `$25.00` authority, and the scientific contract is unchanged.

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
