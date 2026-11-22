# Parallel final token-score experiment handoff

Status, 16 November 2026: experiment 6 completed. All three RTL arms, both wider routed builds and both independent physical comparisons passed. The original circuit and pinned weights are restored and verified, including all 320 original BOS scores. Unique build and measurement evidence is checksum-verified on the Mac. Shared independent backup remains pending. No variant has been adopted automatically. The selected baseline remains scalar-div-v1. No further live operations are pending.

## Explicit physical authorisation

On 16 November 2026, Aidan explicitly confirmed: **Yes, run both comparisons and restore the original.** The confirmation covers temporarily loading the reviewed one-, two- and four-lane circuits for this experiment, followed by restoration and verification of the original circuit and weights. It resolves an automatic-review block that had cited an older no-reprogram instruction. Aidan subsequently explicitly withdrew the standing no-reprogram instruction. It is no longer an active restriction for authorised circuit experiments. Current console authorisation refers to `82180.gradiated-kv260`. Historical replies naming `6796` are not current session instructions. Source, state, health, watchdog and restoration gates still apply to each run.

## Two-lane implementation and completed physical comparison

The [two-lane routed build](../results/logits-2-lanes-build-20261116T161050Z/findings.md) passed independent review of all 318 recovered files, the admitted source closure, route/DRC/timing coverage and programming-image conversion. It meets 50 MHz with +3.766 ns setup and +0.013 ns hold slack. Totals are 34,603 LUTs, 13,202 registers, 31 DSPs and 38 block RAM tiles. The final projection has two DSPs and two weight banks of four RAMB36E2 each. Its activation memory has the same RAM32M16 and two RAM32X1D mapping as the one-lane control. Extra allocated BRAM is therefore in the weight banks.

Physical one-versus-two packet `logits-2-lanes-20261116T164332Z-6c4968`, invocation SHA-256 `950b3b9e41253a1db242d16820d0740a55a942583b1a9a26a2051bf7dce731f8`, passed all 15 gates and 36 timed requests. Independent review recomputed timing, six power traces at five alignments and 18 paired first/last/done counter-delta comparisons. Decode rate rose 4.2–6.5%, completion time fell 2.7–5.7% and gross VCC_SOM energy per output token fell 3.6–4.3%. Original firmware and weights were restored, with all 320 original BOS scores verified. The [completed physical record](../results/logits-2-lanes-20261116T164332Z-6c4968/findings.md) passed reconciliation of all 34 metric definitions, 180 numeric samples and 34 coverage entries.

## Four-lane build and completed physical comparison

The [four-lane build](../results/logits-4-lanes-build-20261116T161510Z/findings.md) meets 50 MHz with +4.776 ns setup and +0.018 ns hold slack. All 318 recovered files and image conversion passed independent review. It uses 34,795 LUTs, 13,367 registers, 33 DSPs and 38 block RAM tiles. Four projection DSPs read four banks of two RAMB36E2 each. Two and four lanes therefore allocate the same eight weight-memory tiles, despite different bank counts. Logical weight bits are unchanged.

One-versus-four packet `logits-4-lanes-20261116T170727Z-020546` passed independent admission, invocation SHA-256 `23eae56ad069c4671c368b6e33789f722bfde009e281dc994576bf4ddbe2a53c`, transfer SHA-256 `ad92f41f8884a1d3e0633ff0b76902adce69a0b1cee330e401d9bd1e227c4d8f`. Its fresh state matched the latest one-versus-two restoration on the same boot, with no new kernel notices.

The [physical comparison](../results/logits-4-lanes-20261116T170727Z-020546/findings.md) passed all 15 gates and 36 timed requests. Independent review recomputed six power traces at five alignments, all 34 metric definitions and 180 numeric samples, and 18 paired first/last/done counter deltas. SOL separately checked absolute first/last/done counts in all 36 timed requests. Both methods agree with simulation. Final original-state SHA-256 is `41503b0cce9962226d0ed6772ec4c3a51973f39bcc9c68bba1ad87fe5baa5dae`. Original firmware and pinned weights were restored and all 320 original BOS scores matched. This does not claim full weight-memory readback.

## Physical results and teaching interpretation

Each row compares its candidate against its own matched one-lane control. Speed ranges cover the three prompts. Energy ranges cover the three paired workload blocks. One useful output token is one byte in this model.

| Change from one lane | Two lanes | Four lanes |
| --- | ---: | ---: |
| Decode tokens/s | +4.2–6.5% | +6.4–10.0% |
| Complete-answer time | −2.7–5.7% | −4.0–8.6% |
| Gross VCC_SOM joules/answer and joules/output token | −3.6–4.3% | −5.7–6.1% |
| Internal first-output saving | 0.1088 ms | 0.1632 ms |
| Additional LUTs / registers / DSPs / BRAM tiles | 56 / 79 / 1 / 1.5 | 248 / 244 / 3 / 1.5 |

The projection itself becomes 1.94× and 3.68× as fast. Whole answers improve less because all other transformer stages still take time and completed scores leave through the same serial interface. Two and four lanes both allocate eight weight-memory tiles. More parallel work needs enough simultaneous memory reads, but physical memory costs rise in blocks. These are measured results on one board and one boot at 50 MHz over three fixed prompts. They do not establish maximum frequency, whole-board energy, concurrent-user capacity or performance on larger models. Two-versus-four is a descriptive comparison through separate one-lane controls, not a directly paired physical test.

Both comparisons use measurement standard v2 with explicit measured, derived, reused and missing coverage. Gross module energy includes inter-request gaps and final verification. Broader serving-load and three-boot repeatability suites remain deferred for this teaching model, and the context sweep is optional.

## Possible workflow improvement, not started

Observed per-candidate routed builds took about 19 minutes. Each serial transfer took about 14 minutes at 115,200 baud, while the subsequent board comparison and restoration took about 5 minutes. Aidan asked about Ethernet. A dedicated Ethernet link for staging and retrieving files could shorten transport while retaining UART for recovery, hashes and bounded execution. No network change has been authorised or made. Before switching, qualify the connection and record a consistent link state and quiet measurement windows. Do not mix different network/power conditions silently in comparisons.

## Completed simulation review

[Matched RTL simulation](../results/logits-lanes-rtl-20261116T161210Z/findings.md) passed all seven cases in all three arms, with exact retained scores, output IDs, stop reasons and valid KV contents. Both wider components passed all 10,240 ordered products and sums per result width, signed rounding/clipping, stalls on every output lane and reset cancellation. All analytical phase and request predictions matched. Only the final projection phase changed.

The coordinator independently checked all 278 archived members, source pins, 75 recorded cycle metrics, 34 measurement-coverage families and exact cache contents across the three arms. Simulation archive SHA-256 `0fdbc1e34f8957942365fecd411552ea6680276f27f1aa1a5f93418b06f0ee74`. Both build-input archives passed independent admission. Both routed builds subsequently passed independent review. These are simulation results, not new physical measurements.

## Question and scope

Can parallel arithmetic shorten the final 320-by-32 token-score projection, and how much does that change whole-request latency, decode speed, module energy and FPGA resources? The one-lane experimental control is the completed `logits-pipeline-v1`. This isolates parallelism from the previous pipelining change. Using that control does not change the selected baseline, which remains `scalar-div-v1` until Aidan adopts another version.

Keep model `chip-joke-text-20261109` W16A16, 50 MHz, existing three natural prompts, exact outputs/stops/cache, host and numerical rules fixed. Parallelise independent output rows, preserving each row's accumulation order and output ordering. Identify any wider or banked weight access needed to feed the lanes as part of the implementation change. Do not describe a simultaneous memory-bandwidth change as a pure arithmetic-only intervention. Separate memory-kind/placement comparisons, DDR, other transformer stages and model changes are outside scope.

## Opportunity and falsification

- Evidence: experiment 5's matched RTL and physical evidence show that the pipelined final projection still runs one lane. Its first-output overhead after the pre-projection boundary is 11,202 clocks in the three natural simulation cases. This includes control/output work and is an upper bound on the first-output saving from this entire region, not a prediction for adding lanes.
- Mechanism: compute distinct score rows concurrently while broadcasting a shared input coordinate and reading a separate weight for each lane. Serialize completed score outputs through the unchanged interface.
- Competing explanations: memory-read capacity, output handshakes, address/control overhead, placement/routing and other transformer stages may limit useful speed-up. Added resources could raise power enough to offset shorter execution.
- Cheapest falsifier: exact component traces must show correct products, per-row sums, ordered outputs, stalls and reset cancellation, then matched model simulation must locate all cycle savings in the changed region.
- Prediction: projection time should fall, with diminishing whole-request gains and increased resources. Exact cycle predictions and resource estimates must be frozen after the design review and before simulation/build. Energy direction is unknown until measured.
- Promotion: exact correctness and routed 50 MHz timing precede physical measurement. A modest gain or regression is still a useful teaching result. No automatic baseline promotion or repeat-until-success performance threshold.

## Reviewed design and analytical prediction

The coordinator accepted SOL's design before simulation. Group L contiguous output rows, broadcast each input coordinate from one read, and read L distinct weights from interleaved row banks. Keep aggregate weight bits and loader addresses unchanged. A group uses one priming read, 32 multiply-and-accumulate clocks, one round clock and L serial output handshakes. No overlap between groups. At continuous ready, predicted `LOGIT_WAIT` clocks are `(34 + L) × (320 / L)`.

| Lanes | Projection clocks | Saved per scored position | Predicted complete-request reduction, Hello / six-byte / max48 |
| --- | ---: | ---: | --- |
| One | 11,200 | 0 | Control |
| Two | 5,760 | 5,440 | 5.71% / 5.23% / 2.66% |
| Four | 3,040 | 8,160 | 8.57% / 7.85% / 3.99% |

These predictions were frozen before simulation and were subsequently matched by simulation and board counters. First-output savings are predicted at 0.1088 and 0.1632 ms at 50 MHz. Bank fragmentation can increase allocated block RAM despite unchanged logical weight bits. Routed reports must establish actual banks, DSPs and supporting logic. Keep one-versus-two and one-versus-four as separate matched comparisons using the existing reviewed harness, each with original-circuit restoration. A derived two-versus-four comparison is descriptive, not its own paired physical experiment. Independent calculation is saved in the coordinator runtime's `predictions.json`.

## Execution and evidence

Follow measurement standard v2's core circuit-comparison scorecard. Run component tests and the existing seven-case matched model replay, preserving historical fixtures and all earlier source versions. Then review a bounded routed build on the existing Linux host. Unique sources, build outputs, programming images and raw results must be copied and checksum-verified on the Mac. The temporary server is not durable storage.

The protocol and invocation fix exact source hashes, simulator/build limits, physical arm ordering, warm-ups, repeats, deadlines, stop rules and evidence size before each stage. Reuse the existing trusted host and power path. Record TTFT, decode TPS, complete-answer time, output counts, valid outcomes, active/idle VCC_SOM power, gross joules per answer/token, tokens/J, LUT/register/DSP/BRAM counts and percentages, memory organisation and routed timing. Use existing simulation/board counters for local and complete-request attribution. VCC_SOM is module-supply energy, not whole-board energy. Short repeats are sufficient for this scoped teaching comparison, with variability and claim limits visible.

SOL is the sole server/board owner. Qualify current console, boot, source/image/weight pins and administrator access before physical dispatch. Temporarily load only the reviewed arms and restore the original research circuit and pinned weights, verifying the original 320 BOS scores on healthy completion. Preserve failures and partial evidence, stop unsafe operations and keep restoration state explicit. No new compute reservation, shared CI, publication, commit, push or deployment is included.

## Ownership

Checkout `/Users/aidanmcconnell/dev/gradiated-hardware-wip`, branch `hardware/research-and-articles-wip`, starting HEAD `8f67839f3643dfdb89c554e4bafab6d9d3f0ba72`. Initial hashes cover 4,165 existing files at `.agents/runtime/hardware/inference/outputs/logits-lanes-v1-coordinator/initial-files.json`.

SOL chat `01a1301d-6afb-7053-b238-354703c4cb49` owns new variants, tests, protocol, immutable run records and sole live execution. Coordinator chat `01a1d0ea-a381-7050-8265-ff2310b83101` owns this handoff, indexes, private article progress and independent audits. Aidan is editing article `script.md` concurrently. Do not edit article prose or figures. Preserve all experiment 5 and milestone-preparation working changes. Independent shared artifact backup remains pending.
