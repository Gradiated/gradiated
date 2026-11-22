# Scalar multiplier experiment handoff

Status, 16 November 2026: **complete, independently audited, original circuit and weights restored**. All 15 gates and five firmware switches passed. All 320 original BOS scores matched after restoration. SOL confirmed the console detached and no further board work. Do not rerun the dispatched packet. No commit, push or deployment occurred.

## Decision and change

Aidan adopted prefill-skip-v1 and authorised experiment 3, scalar multiplication acceleration. The model remains chip-joke-text-20261109, with unchanged division, numerical rules, host reader, workloads, cache layout and 50 MHz clock. Only fixed_scalar.sv changed: the exact multiplier consumes four bits per calculation step instead of one, reducing its loop from 64 cycles to 16. All five scalar instances use the new implementation. DSP sharing remains a separate future proposal.

On 16 November 2026, Aidan adopted **scalar-mul-v1** as the selected baseline. The frozen model remains unchanged and all earlier versions and measurements are preserved. Decide the next experiment with Aidan before running anything. Adoption is a repository selection, not a board reprogramming action. The user subsequently shut the board down for the night. Current power, boot and console state have not been checked since returning, so any future run needs fresh state checks and a newly reviewed packet.

## Evidence

- [Variant](../implementations/kv260/variants/scalar-mul-v1/README.md) and [frozen protocol](kv260-scalar-mul-v1.md).
- [Simulation](../results/scalar-mul-rtl-20261115T234330Z/findings.md): seven exact full-model cases and 3,567 mixed scalar-oracle operations, including all multiplier reset offsets. The coordinator independently checked 1,671 direct multiplication fixtures, the full-width arithmetic invariant and all fourteen request boundary savings. All 183 archived simulation members verified on the Mac.
- [Build](../results/scalar-mul-build-20261116T001040Z/run.json): setup/hold slack 3.887/0.012 ns at 50 MHz, full route and clean clock coverage. 33,993 LUTs, 12,828 registers, 30 DSPs and 36.5 BRAM tiles. Relative to prefill-skip-v1: +818 LUTs, −884 registers, +20 DSPs and unchanged BRAM. Four added DSPs implement each of the five scalar multipliers. All 316 build files, 17 build inputs, 11 RTL modules and exact bit conversion independently verified. The build has 72 unwaived DSP pipeline advisories (12 input, 30 PREG and 30 MREG), with zero errors or critical warnings. See server/build/reports/drc.rpt in the recovered archive.
- [Physical findings](../results/scalar-mul-20261116T001133Z-268099/findings.md), [immutable record](../results/scalar-mul-20261116T001133Z-268099/run.json) and [independent audit](../results/scalar-mul-20261116T001133Z-268099/audit-manifest.json): 36 timed requests and 18 warm-ups across three AB/BA/AB pairs, 139,840 signed diagnostic scores, three compact smokes and two cap checks. All passed. First-token time fell 27–32%, decode rate rose 24–30% and complete-request time fell 22–24%. Module energy per verified answer fell 22.1–22.5%, with almost unchanged active power. All 18 measured first/done cycle savings matched simulation exactly.

The independent audit decoded all 15 serial gates, recalculated 36 timing requests and six 350-sample power traces across five alignment cases, and reconciled 34 metric definitions, 180 numeric samples and 27 coverage entries. All 264 raw artifacts verified. Energy is VCC_SOM module supply, not whole-board or FPGA-only energy. Evidence covers three prompts, one board and one boot. Pure physical prefill timing, physical AXI bandwidth, host peak memory and long-term stability remain outside this test. Restoration verifies the firmware/weight reload and original inference behaviour, not full weight-memory readback.

## Exact identities and recovery

- Active checkout: /Users/aidanmcconnell/dev/gradiated-hardware-wip, branch hardware/research-and-articles-wip, HEAD 04c7100ca9d5ba9ddbd49fdc14bd85cefcc6381d.
- Physical packet: `.agents/runtime/hardware/inference/outputs/scalar-mul-20261116T001133Z-268099/`.
- Invocation SHA-256: `8a220cce716949251602ebd7f67a9aa7ee79c018da72830698de99982306aee4`.
- Transfer SHA-256: `99d4edad26a4d8f90962ff0d87408ec0e033f490a9bb1c2c6106c33ccd6479a0`.
- Candidate programming file SHA-256: `b361611b97d720b99c727103202905ad2229bcb8d5e06d0e78bad8cecffefffa`.
- Control programming file SHA-256: `6ae36d72a8045c1dac2c7af28c840ab136c74e6e58360531bec51fde0370088a`.
- Run record SHA-256: `622c9f4d2c459afe78ea0ba0e62eeb60b9351f70b33f5cd3238496019261e191`.
- Raw manifest SHA-256: `8fbb08689214802bf458ca8af66f32a71a662d7e88ba3bbe7d029020d2d3d70d`.

Both arms use AU02 and the identical native reader. Firmware hashes distinguish the arms. Sources and outputs are preserved on the Mac. Audit scripts, results and the initial file snapshot are in the sibling `-audit` directory. The recovered build is under `.agents/runtime/hardware/inference/outputs/scalar-mul-build-20261115T234735Z-recovery/`. No unique artifact depends on the temporary Linux server. Shared artifact backup remains pending.

## Execution history and ownership

SOL chat 01a1301d-6afb-7053-b238-354703c4cb49 owned implementation, tests, protocols, records and sole board/server execution. Coordinator chat 01a1d0ea-a381-7050-8265-ff2310b83101 owned adoption/index documentation and independent review/audit. Existing WIP and historical variants/records were preserved.

The first build connection failed at hostname lookup before contacting the server. Target absence was checked before one direct-address launch. The build completed within its 2,520-second build and 2,700-second archival limits. The first board attempt stopped at administrator authentication, before staging or dispatch, and is preserved as stop-2458912a.json. Aidan privately refreshed authentication and confirmed zero and detach. SOL released only the stale display of that exact Screen session, then resumed the unchanged packet. Transfer, post-transfer authentication and all execution/restoration gates passed. The initial authentication stop is separate from zero failures in the accepted inference comparison. Screen 6796.gradiated-kv260 is detached. New board work requires a new reviewed packet and current-state checks.
