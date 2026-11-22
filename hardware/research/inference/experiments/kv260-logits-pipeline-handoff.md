# Final token-score pipeline experiment handoff

Status, 16 November 2026: **experiment 5 complete, original circuit and weights restored and verified**. The [physical comparison](../results/logits-pipeline-20261116T143416Z-2592fd/findings.md) passed all 15 gates, 36 timed requests and exact output checks. Across the three matched pairs, decode rate increased 7.3–11.1%, complete-request time fell 4.6–9.4%, and gross VCC_SOM module energy per output token and per verified answer fell 6.6–6.7%. The internal first-output boundary improved by exactly 9,920 clocks, or 0.1984 ms at 50 MHz. Host-observed first-output differences are small and include scheduling variation. All 18 matched first/last/done counter deltas agree exactly with simulation.

The [routed build](../results/logits-pipeline-build-20261116T130030Z/findings.md) meets 50 MHz with +4.725 ns setup and +0.029 ns hold slack, 14 additional LUTs and 11 registers, unchanged DSP and block RAM counts. All 318 recovered build members, admitted source pins and programming-image conversion passed independent review. The first aborted build is preserved separately.

The independent physical audit decoded all 15 gate exports, checked every timed output, recomputed six power traces at five timestamp alignments and checked all timing metrics against the compact record. Power is VCC_SOM module-supply energy, not whole-board or FPGA-only energy. The three fixed prompts and short matched repeats establish a result on this board and boot, not broad model or long-run performance.

Final board state: original research circuit and pinned original weights restored, all 320 original BOS scores checked, 50 MHz, boot 305f2b01-e9fd-4461-8e6d-0cf91979d151. Full configuration and weight-memory readback were outside scope. SOL owns the 82180.gradiated-kv260 console. Before a later run, check its current existence/owner, boot and private administrator authorisation rather than assuming this state persists.

**Selected baseline remains scalar-div-v1.** No automatic adoption, later experiment, commit, push or deployment is authorised by this result. Discuss adoption and the next experiment with Aidan. Raw evidence is saved on the Mac under `.agents/runtime/hardware/inference/outputs/logits-pipeline-20261116T143416Z-2592fd`, the build under `logits-pipeline-build-20261116T130030Z`, qualification under `logits-pipeline-qualification-305f2b01`, and independent scripts/results under `logits-pipeline-v1-coordinator` in the same outputs directory. Independent shared artifact backup remains pending.

## Scope and hypothesis

Compare scalar-div-v1 with a separately identified logits-pipeline-v1, on the frozen chip-joke-text-20261109 W16A16 model at 50 MHz. Change only scheduling inside the final 320-by-32 token-score projection. Fetch the next operand pair while multiplying and accumulating the current pair, retaining one arithmetic lane, the same memory ports, operand order, exact accumulator/rounding/saturation, output ordering and backpressure/reset behaviour. Other dense instances, scalar arithmetic, model, native host reader, cache and workload remain unchanged.

The baseline alternates READ and MAC states. An initial analytical estimate is 31 saved clocks per row, or 9,920 clocks (0.1984 ms at 50 MHz) per scored position. With the existing three natural prompts, this is approximately 4.62–9.43% of complete-request simulated cycles. These are predictions, not results. Simulation must establish the actual critical-path effect, including stalls and row transitions. Scalar division remains material, so this proposal does not claim matrix operations dominate all remaining time.

Competing explanations are memory-read latency, output backpressure or implementation timing hiding the apparent saving. Component and matched full-model simulations are the first falsifiers. The routed build must preserve memory/DSP inference or explain any change and meet the unchanged clock. Physical comparison then tests whether cycle savings translate into host-observed latency and VCC_SOM energy. Adding more arithmetic lanes and further scalar division changes remain separate experiments.

## Gates and evidence

Follow inference-measurements-v1 and the new frozen protocol before execution. Use exact component oracle checks, matched seven-case model simulation, then a reviewed bounded Vivado build on the existing server. Preserve unsuccessful attempts. Recover and hash unique artifacts on the Mac before relying on the temporary server.

After reviewing the build and physical packet, qualify the fresh board boot and the original project state. Compare matched control/candidate runs using the existing timing, output and VCC_SOM measurement boundaries, then restore and verify the original circuit and pinned weights. Board availability and private authentication may require Aidan's input. Do not reuse an earlier dispatched packet or boot-specific warning anchor. No model retraining, other circuit experiment, new compute reservation, automatic baseline promotion, commit, push or deployment is included.

## Ownership and continuation

Checkout: /Users/aidanmcconnell/dev/gradiated-hardware-wip, branch hardware/research-and-articles-wip. Starting commit: 8f67839f3643dfdb89c554e4bafab6d9d3f0ba72, already pushed. The initial tracked-file hashes are in .agents/runtime/hardware/inference/outputs/logits-pipeline-v1-coordinator/initial-files.json.

SOL chat 01a1301d-6afb-7053-b238-354703c4cb49 owns new variant sources, tests, protocol, immutable run records and sole server/board execution. Coordinator chat 01a1d0ea-a381-7050-8265-ff2310b83101 owns this handoff, indexes, private article progress and independent review/audits. SOL should challenge decisions independently and return simulation/source pins before build admission. Both preserve unrelated work. Raw evidence, weights and bitstreams remain outside Git, with shared independent backup pending.
