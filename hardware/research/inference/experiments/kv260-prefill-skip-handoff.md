# Prefill score skipping handoff

Status, 15 November 2026: **comparison complete, independently audited and original circuit and weights restored**. All 15 gates passed. The original 320 BOS scores matched after restoration, the FPGA manager was operating and flags/taint were zero. The console is detached and no experiment remains running. Do not rerun the dispatched packet. The earlier authentication-only stop is preserved. No commit, push or deployment. Aidan subsequently adopted `prefill-skip-v1` and authorised a separate scalar multiplication experiment. See the [baseline decision](../implementations/kv260/README.md#selected-circuit-comparison-baseline).

The user selected this experiment on autonomous-v1 with the standard measurements. Automatic approval review rejected sending the execution instruction, citing an earlier no-reprogramming constraint. Aidan then explicitly confirmed: “Yes — run the comparison and restore the original”, in response to the question naming temporary loading of autonomous-v1 and prefill-skip-v1 and restoration of the original circuit and weights. That resolves the scope conflict for this reviewed comparison. The private authentication refresh was received and the post-transfer administrator check passed before dispatch. This does not authorise another experiment or a changed packet.

## Preserved evidence

- [Variant](../implementations/kv260/variants/prefill-skip-v1/README.md) and [frozen protocol](kv260-prefill-skip-v1.md).
- [Simulation record](../results/prefill-skip-rtl-20261115T221207Z/run.json): seven cases, 103,360 retained score checks, matched cache at prompt boundary and completion. Exact saving 21,121 cycles per omitted position, no physical performance claim.
- [Build record](../results/prefill-skip-build-20261115T224330Z/run.json): all 316 archive members recovered and verified on the Mac, 50 MHz timing, setup/hold slack 5.342/0.013 ns, 33,175 LUTs, 13,712 registers, 10 DSPs and 36.5 block RAM tiles.
- Verified runtime build archive: `.agents/runtime/hardware/inference/outputs/prefill-skip-build-20261115T220726Z-recovery/server.tar.gz`, SHA-256 `147b73c6f5d1f20af5288cf20ca593acac324143c52677d5a25d613f42b2c4c5`. Shared artifact backup remains pending.

## Exact reviewed physical packet

All runtime paths are relative to the repository root. Packet: `.agents/runtime/hardware/inference/outputs/prefill-skip-20261115T224422Z-754f19/`.

| Item | SHA-256 |
| --- | --- |
| `invocation.json` | `b5859231b43bccfe5c14ea9a23825f12e26c4dbfb19162209e26621f8ec75dd7` |
| `board-transfer.gz` | `0104f75705335d1ca70033c92130cc1b0f9523b4d9b0095ca25f54cd0f33032a` |
| Frozen protocol | `1b0eb6810ec883f8c005bac3c551d80d2488204f442e2f6c3dfdca9ba07c5c59` |
| Candidate firmware | `6ae36d72a8045c1dac2c7af28c840ab136c74e6e58360531bec51fde0370088a` |
| Autonomous-v1 control firmware | `071f8cf91657fb5446e66754c28795faa52b92ca2e4aa6ddba71859b1396e3a9` |

Independent review checked all 29 captured source/asset hashes, 22 decoded transfer members, 15 gates and five firmware switches. The compiled overlay differs from the control only in firmware-name. Both arms use the same autonomous output collection path. Post-transfer sudo validation precedes the dispatch-intent marker, so expiry can stop before dispatch and resume from a verified staged receipt.

The completed packet checked its pinned boot and last accepted restoration warning reference. The final console is detached `6796.gradiated-kv260`. Any future experiment needs its own reviewed packet and state checks. Do not reuse this dispatched packet or place passwords in files or chat.

## Completed sequence and next decision

1. The initial authentication-only stop occurred before dispatch and is preserved separately from the accepted comparison. After private refresh, the unchanged packet transferred and passed its post-transfer administrator check.
2. All 15 gates completed, including three AB/BA/AB pairs with 36 timed requests and 18 warm-ups. Full-score diagnostics checked 139,840 signed scores. Compact completions, stops and context counts matched, including zero-byte and one-byte caps.
3. The original firmware and pinned weights were restored. All 320 original BOS scores matched. This verifies the reload and original inference behaviour, not full weight-memory readback.
4. Raw evidence is preserved on the Mac. The independent audit decoded all gates, recalculated timings and six power traces across five timestamp alignments, checked the exact cycle savings in 18 matched request pairs and reconciled all 34 metric definitions, 180 numeric samples and 27 coverage entries. All 262 raw artifact hashes verified.
5. Closeout decision, subsequently updated: Aidan adopted prefill-skip-v1 and authorised experiment 3, exact scalar multiplication acceleration. That experiment must use a new protocol and execution packet. This completed packet must not be rerun. No commit, push or publication is authorised.

[Physical findings](../results/prefill-skip-20261115T224422Z-754f19/findings.md), [immutable run record](../results/prefill-skip-20261115T224422Z-754f19/run.json) and [independent audit manifest](../results/prefill-skip-20261115T224422Z-754f19/audit-manifest.json). First-token time fell about 13–15%, decode rate stayed unchanged and VCC_SOM module energy per verified answer fell 2.7–3.1%. Active power was nearly unchanged, so lower energy reflects shorter work. This is three prompts on one board in one boot, not whole-board energy or long-term stability.

The audit scripts, results and initial file-hash snapshot are preserved beside the packet in the `-audit` directory. Build and simulation artifacts are verified on the Mac. No Linux process needs to remain running, and no unique artifact depends on the temporary server. Shared artifact backup remains pending.
