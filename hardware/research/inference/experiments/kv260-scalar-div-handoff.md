# Exact division experiment handoff

Status, 16 November 2026: **complete, independently audited, original circuit and weights restored**. All 15 gates and five firmware switches passed. Original 320 BOS scores matched after restoration. SOL confirmed Screen 39535.gradiated-kv260 detached and no further board/server work. Do not rerun the dispatched packet. No commit, push or deployment occurred. Aidan subsequently adopted scalar-div-v1 on 16 November 2026.

## Decision and change

Aidan authorised experiment 4 from the adopted scalar-mul-v1 baseline, with SOL and inference-measurements-v1. The separate scalar-div-v1 circuit replaces only the generic scalar divider. It computes two quotient bits per step with parallel differences against B, 2B and 3B. Thirty-two calculation steps plus one finish step replace 64 calculation steps, saving 31 cycles per division. Exact quotient, raw remainder, ties-to-even rounding, signed limits, invalid inputs and protocol behaviour are preserved. The frozen chip-joke-text-20261109 model, multiplier, tables, cache layout, AU02 interface, native host reader and 50 MHz target are unchanged.

**Scalar-div-v1 is the selected baseline**, adopted by Aidan on 16 November 2026 after reviewing the completed comparison. The frozen model remains chip-joke-text-20261109. Preserve scalar-mul-v1 and all earlier versions, measurements and failed attempts. Adoption updates the repository selection, not the circuit loaded on the board. The next experiment remains for discussion and is not authorised to run.

## Evidence

- [Variant](../implementations/kv260/variants/scalar-div-v1/README.md) and [frozen protocol](kv260-scalar-div-v1.md).
- [Simulation](../results/scalar-div-rtl-20261116T102115Z/findings.md): seven paired full-model cases, 103,360 retained scores per arm, identical outputs/stops/cache contents. 3,668 mixed scalar commands, 1,772 direct DIV fixtures and 4,962 raw quotient/remainder traces passed. Reset covered all 64 baseline and 33 candidate offsets, including the finish step. All fourteen boundary savings equal 31 cycles per division. The coordinator independently checked the recurrence, rounding fixtures, source closure and all 225 archived files.
- [Build](../results/scalar-div-build-20261116T104711Z/findings.md): 50 MHz, setup slack 3.722 ns, hold slack 0.031 ns, fully routed and timing-covered. 34,533 LUTs, 13,112 registers, 30 DSPs and 36.5 BRAM tiles. Relative to scalar-mul-v1: +540 LUTs, +284 registers, unchanged DSP/BRAM. The 72 existing DSP pipeline advisories remain, with zero design-rule errors or critical warnings. All 316 archive members and programming-file conversion verified on the Mac.
- [Physical comparison](../results/scalar-div-20261116T105755Z-3c2ae0/findings.md) and [independent audit](../results/scalar-div-20261116T105755Z-3c2ae0/audit-manifest.json): 36 timed requests, 18 warm-ups, three AB/BA/AB pairs. First-token time fell 24–27%, decode rate rose 30–35%, completion time fell 23–27% and gross module energy per verified answer fell about 25%. Active power stayed around 3.12–3.13 W. All 18 first/done counter comparisons match simulation. Exact diagnostics checked 139,840 signed scores, with matching compact completions and cap checks.

The independent audit redecoded all 15 serial gates, recalculated 36 request timings, integrated six 350-sample traces under five timestamp alignments, reconciled 34 metrics/180 numeric samples/27 coverage entries and verified all 266 raw files. Energy covers VCC_SOM module supply, including the same verification work and request gaps, not whole-board or FPGA-only energy. Scope is three natural prompts, one board and one boot. Physical pure-prefill timing, physical AXI bandwidth, host peak memory and long-term stability remain outside this comparison. Restoration verifies reload and original inference behaviour, not full weight-memory readback.

## Exact identities and recovery

- Checkout: /Users/aidanmcconnell/dev/gradiated-hardware-wip, branch hardware/research-and-articles-wip, HEAD 04c7100ca9d5ba9ddbd49fdc14bd85cefcc6381d.
- Variant manifest SHA-256: 73123c2c753093e1e359de64a98b98e48471382ba4bd85758108ab7a78944f13.
- Candidate programming file SHA-256: 22f5d16ed47cf25c3c793d82ee18242b5b635f49e916a13a8b9ed750dd70fb0d.
- Control programming file SHA-256: b361611b97d720b99c727103202905ad2229bcb8d5e06d0e78bad8cecffefffa.
- Packet: .agents/runtime/hardware/inference/outputs/scalar-div-20261116T105755Z-3c2ae0/.
- Invocation SHA-256: e6475419fd77096d5c1cd6b202d58bcd7d1bce626cef1abbfd853b04a381a9a1.
- Transfer SHA-256: 7caf0dcc2929e3cd5700c505d4cf887c7339602425251348ffc0750e107f696b.
- Run record SHA-256: 4d7c75c293ea94145b925f49d83ca8423c8e4754ca681019f192adc8e5b4e451.
- Raw manifest SHA-256: 4c91f15b76ed450c944a0b4606406064abea94c70ba1238d5cc1764033a52b3d.
- Boot: 61891471-8bdf-44b7-bfd7-0613d816e0fe. Original project-state/warning anchor SHA-256: 30f6e347dd11c852fa9bda695037876b257fdfa9624172aff8a1781a03de0cbe.

Raw build recovery is in .agents/runtime/hardware/inference/outputs/scalar-div-build-20261116T102609Z-recovery/. Initial boot capture and completed stock setup are preserved separately as scalar-div-qualification-61891471 and scalar-div-original-setup-61891471. Root audit scripts, results, admission receipts and initial file snapshot are in the physical packet's sibling -audit directory. All unique sources and outputs are verified on the Mac. The temporary Linux server holds no unique experiment artifact. Shared independent backup remains pending.

## Execution history and ownership

SOL chat 01a1301d-6afb-7053-b238-354703c4cb49 owned implementation, tests, protocols, immutable run records and sole server/board execution. Coordinator chat 01a1d0ea-a381-7050-8265-ff2310b83101 owned indexes, this handoff, private publishing progress and independent audits.

The first scalar test parser counted a repeated post-reset fixture twice under its fixture ID. SOL preserved the failure, changed accounting to request ordinal and reran both arms without changing RTL. A fresh boot had the starter image, so the reviewed original-project setup ran before the comparison. Automatic approval review initially cited an old weights-only no-reprogram restriction. Read-only inspection established the later circuit-test authorisations and current experiment request, and the same instruction passed on retry with this evidence. No rejection was bypassed. App-level Bad Request interruptions during coordination/local saving were recovered without duplicate board dispatch.

Aidan privately refreshed sudo, then explicitly asked us to detach. SOL detached only the named session. Initial and post-transfer authentication/boot checks passed. The 5,160 transfer chunks and all subsequent measurement/restoration gates passed. Final manager is operating with flags zero and taint zero. Boot firmware, SD/QSPI and authentication policy were not changed. The question about reducing password prompts remains a separate setup discussion. New work needs current state checks and a new reviewed packet.
