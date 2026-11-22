# Resume KV260 roadmap steps 1–3

Steps 1–3 reached the agreed bounded stopping point on 15 November 2026. The counter circuit completed its reviewed physical comparison and passed exact-output, counter and restoration checks. Timing neutrality remains inconclusive. The original circuit and weights are restored, raw evidence is verified on the Mac, and both agents have stopped before roadmap step 4. Decide the wider experiment set together. The dated preparation and approval history below is preserved.

## Working state and ownership

- Active repository: `/Users/aidanmcconnell/dev/gradiated-hardware-wip`, branch `hardware/research-and-articles-wip`, HEAD `04c7100ca9d5ba9ddbd49fdc14bd85cefcc6381d`. Work is local and uncommitted. Inspect status/diffs and applicable AGENTS before resuming. Preserve all existing changes. No commit, push, PR or deployment is authorised.
- Original checkout `/Users/aidanmcconnell/dev/gradiated` remains on `FPGA-deep-dive`, HEAD `21377c594`. Its unrelated Ashby edit remains intact, SHA-256 `eaeb7ea6e2c4c1a252707afa6e4ae40eb3a4829a9d621c16bd54f05f3e4f9b0e`. Do not change it or other people's website work.
- Astra chat: `01a1d0ea-a381-7050-8265-ff2310b83101`. SOL chat: `01a1301d-6afb-7053-b238-354703c4cb49`, host `local`. User authorises two-way coordination. SOL independently critiques decisions and is the sole UART/board operator. Astra owns counter RTL/build and independent review.
- Frozen model remains `chip-joke-text-20261109`, W16A16, unchanged. The original wrapper and original bitstream remain the baseline for step 3.

## Completed steps 1 and 2

[Findings](../results/resident-score-extraction-20261115T172914Z-489050/findings.md), [run](../results/resident-score-extraction-20261115T172914Z-489050/run.json), [independent audit](../results/resident-score-extraction-20261115T172914Z-489050/audit-manifest.json), and [tested source](../implementations/kv260/variants/ctypes-slice-v1/README.md).

- 12 diagnostic, 18 warm-up and 36 timed requests, all exact checks passed. Original weights restored and 320 original BOS scores verified. The earlier 80.54 ms verification outlier did not recur and remains unexplained. Two smaller delays overlapped 4–5 ms of garbage collection.
- One candidate changes `list(values)` to `values[:]` for the 320 returned signed scores. Generation time fell 5.48–5.57% in three matched pairs. Verified output rate rose from 144.05–144.24 to 152.11–152.38 bytes/s. Gross VCC_SOM energy fell from 2.317–2.319 to 2.185–2.187 J/completion.
- Evidence is one boot and one loaded session, module-rail power only. No whole-board or FPGA-only energy claim. Mac independently re-decoded UART exports, checked all 11 gates and reference receipts, and separately integrated six 350-sample traces across five timing-alignment cases.
- Run SHA `6d480805e190e34bd12f410a3019483550b5913f3f29d34ffe32a1473cd693ce`. Capture-manifest SHA `75cfd7d94574887fd8140b49c35903823b1fbd4e1a95580048c5e2dc47683581`. Audit was attached separately after sealing, preserving original records.

## Step 3: prepared, not physically qualified

[Protocol](kv260-observer-v1.md) and [source](../implementations/kv260/variants/observer-v1/README.md). Four RTL overrides materialise against eleven pinned baseline files. The original RTL is untouched.

Final Git-source simulation harness passed: two BOS requests and 640 exact scores, cycle-identical original/variant legacy AXI traces, phase and handshake counters, idle read stability, context clear, synthetic busy/reset races and saturating overflow. Snapshot validator rejects deliberate corruption. These are simulation evidence, not board measurements.

Counter snapshots must follow the entire power window, never sit between scored requests. Phase counters partition busy time. Other event counters overlap those phases. Cache wait counters detect extra bubbles, not all memory-access cost. Validate N tokens, 320*N scores, 32*N*(N+1) cache-pair transfers, no fault/overflow and stable idle reads.

Offline Vivado 2025.2 build completed generate (30 s), synth (409 s), opt (89 s), place (267 s). Routing was explicitly terminated for the user pause after 278 s, exit -15, before a routed DCP existed. It was not a numerical or timing failure. Reports, bitstream generation and physical qualification remain undone.

## Saved build and preparation

Mac recovery root:
`/Users/aidanmcconnell/dev/gradiated-hardware-wip/.agents/runtime/hardware/inference/outputs/observer-20261115T1735-preparation/`

- `server-paused.tar.gz`: expected SHA `a80e812118959082fdf82fd99b91a84b72e853b44228ace76903192f35468459`, 35,260,240 bytes. `server-paused/observer-20261115T1735/` holds its extracted tree. Check `pause-recovery-verified.json` before trusting recovery.
- `server-paused/.../paused-files.json` identifies 258 files (60,073,129 bytes), with no symlinks. `build/place/place.dcp` is the restart checkpoint. `build/route/` preserves interrupted logs. All prior source-closure, clock, structure and phase records are retained.
- `mac-workbench-paused/` preserves temporary source-generation scripts, tests, fixtures, logs, notes and the final harness results, excluding rebuildable compiler object directories.
- `build-packet/` and the archived server tree contain the exact derivative Tcl build script and phase runner.

Server: `admin@100.73.61.0` on existing tailnet. Working SSH uses `/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=8 admin@100.73.61.0`. Do not depend on MagicDNS. Existing Vivado is `/home/admin/amd/2025.2/Vivado/bin/vivado`. Isolated build root is `/home/admin/projects/gradiated/.agents/runtime/fpga-inference/observer-20261115T1735`. No build should be running after this pause. Preserve the server's unrelated authoring edit and all prior directories. The server is temporary, so copy and verify all new artifacts on the Mac.

Resume routing from `build/place/place.dcp` into a **new** output directory such as `build/route-resume1`. Do not delete or overwrite interrupted `build/route/`. Preserve the original runner and use a separately recorded derivative that selects the fresh output and routes subsequent reports/bitstream phases to the new routed DCP. Enforce the original two-thread, 600-second route and 180-second reports/bitstream caps and process-group cleanup. Review clock topology, routing, DRC, slack, source identity and utilisation before any bitstream preparation. No waivers or optimisation search.

Offline reader: `observer_read.c` source SHA `aee107f6422189f33e66bb00d3677c8226f5637fe97689bdec238c725f4ef34b`, ELF `libobserver_read.so` SHA `5e7cb26e51ec883ceb98c06d43b1ac9658bf7949dc9bb2911e1403ca833438d1`. It reads the existing owned UIO mapping with aligned 32-bit reads and `dsb sy` barriers. No original native-library change. Disassembly inspected, no unresolved symbols.

Observer program DTBO SHA `947e1ee5aa19bb82dac9151dd0ef0719df8cb0fdb637f6e7484f413a9c025e51`. Only firmware-name changes to `gradiated-tiny-observer-v1-50mhz.bit.bin`. Offline resolution against the archived board tree verified reset 119 and 50 MHz with unchanged clock/interface overlays. A first resolution command used a missing input path, then succeeded with verified archived DTBO paths. No board action occurred.

SOL's physical-packet preparation and handoff:
`/Users/aidanmcconnell/dev/gradiated-hardware-wip/.agents/runtime/hardware/inference/outputs/observer-physical-preparation-20261115/resume.md`

Its `build/` contains unfinished lifecycle, host and board supervisors, tests and pinned helpers. Synthetic tests replay 14 gates, four simulated switches, 36 timed, 18 warm-up and three smoke requests. A missing benchmark_validation.py dependency was fixed and full mock freeze→run assembly tested. The real packet still needs actual accepted assets and independent review. Never mistake synthetic stock-byte fixture packages for an observer image. No real observer packet has been frozen, staged or dispatched.

## Board and authority at pause

The software run ended successfully. Its last restoration gate at 17:39:25 UTC verified the original firmware `gradiated-tiny-50mhz.bit.bin` and all 320 original BOS scores. SOL confirmed no active board supervisor or UART operation. Screen `29312.gradiated-kv260` was detached and the sole serial owner before restart. A Mac restart will invalidate that PID/session assumption. Board boot was `0e4cc12e-4532-4434-be89-665af09dba14`. USB reconnect or reboot requires fresh preflight. Do not issue concurrent UART commands from Astra.

Automatic approval review rejected a proposed programming-coordination message, citing an earlier no-reprogram restriction. **No observer programming is authorised for execution until explicit fresh user approval, after concrete artifact/packet review.** Finish bounded offline checks first, then ask about the exact temporary counter-image qualification and original-image restoration. Do not bypass the review. Healthy planned comparison has four switches with original restoration at the end. Any abnormal state, hardware failure or lost acknowledgement is fail-stop, preserving state for separately reviewed recovery.

No power-off or reboot of the FPGA was requested during this pause. Passwords remain in the user's private terminal. Ask for a private sudo refresh only when a reviewed live packet is ready and sudo has actually expired.

## Completed after restart

The [offline build record](../results/observer-build-20261115T180508Z/run.json) and [findings](../results/observer-build-20261115T180508Z/findings.md) are the current implementation status. Earlier pause descriptions above remain historical.

- New `build/route-resume1`, `reports-resume1` and `bitstream-resume1` passed in 500.30, 72.07 and 113.98 seconds. No original output directory was overwritten. Setup slack +4.725 ns, hold +0.013 ns, complete routing and clock coverage, no DRC errors or critical warnings. The same 32 DSP-pipelining advisories remain without waivers.
- Routed totals: 32,553 LUTs, 12,044 registers, 10 DSPs, 36.5 block-RAM tiles and 5,764 occupied CLBs. The original implementation remains the comparison baseline.
- Under the Mac recovery root above, `server-resumed.tar.gz` is 57,530,771 bytes, SHA `8c7a2ed6f2c8e5b15485e573aa60a2bd137ebb60818e4c644991dcabe1cc3abd`. Its extraction is `server-resumed/observer-20261115T1735/`. All 327 inventoried files passed checksum checks, and all 258 pre-restart files are unchanged. `resumed-build/offline-acceptance.json` records independent checks, source pins, timings and resource counts.
- Observer firmware: extracted `offline-package/gradiated-tiny-observer-v1-50mhz.bit.bin`, 7,797,692 bytes, SHA `2a3559bc1cd39e627b35d72c8a55a4b49a06640f48ab23dab884429fa5af0390`. Mac independently verified the exact Bootgen payload conversion. Reader and overlay pins above are unchanged. No observer image has been programmed.
- SOL’s new flat checkpoint is `.agents/runtime/hardware/inference/outputs/observer-physical-preparation-resumed-20261115/`, with `review.md` and `checkpoint-manifest.json` (SHA `7deca18c700f40260b3c3c23f167a12c12b68bd99a5c4a40f3211a40ec1e8064`). All 24 artifacts were verified. A future invocation must explicitly select the current dedicated Screen session and match the pinned boot before staging. Synthetic replay and assembly tests passed. No UART access occurred.
- SOL independently confirmed unchanged generated clock/reset wiring. Separate review: `.agents/runtime/hardware/inference/outputs/observer-physical-preparation-resumed-20261115-reset-review.md`, SHA `021a858fbc4fffb9b883fcef55d09dc566fafbb8022880fb65f45998813b8a55`.

## Reviewed physical packet and pre-run sequence

The actual observer packet is saved at `.agents/runtime/hardware/inference/outputs/observer-qualification-20261115T182057Z-11c575/`. Its `invocation.json` SHA is `912cdc0af81989f8f0b9b14ddfc1817f69516466bc32a6843cfa62c2a8271c2e`. Independent review verified all 25 captured sources, all 18 compressed-transfer members, accepted firmware/reader/overlay pins, the current protocol and the complete schedule. The protocol SHA is `7e81a34ccc1ebbc3b30b804d9710a7826080c2f8d92540091c522d0a1ffe1ddd`. Do not silently change this protocol after freezing the packet.

The transfer is 1,175,245 compressed bytes and 2,449 chunks, within the separate 540-second staging limit. Physical execution has a 1,050-second outer limit and 1,030-second supervisor limit. A current, detached, exclusively owned dedicated Screen session and matching pinned board boot are required. A legitimate reboot needs a separately reviewed session baseline, not a bypass of the boot check.

The Mac build recovery root contains `resumed-build/physical-packet-review.json` with the independent review. No `staged.json`, `dispatch-intent.json`, physical `result.json` or gate log existed at review. No UART operation occurred in the resumed turn. SOL is paused before physical action. The original checkout’s unrelated Ashby edit still matches its saved hash. No commit, push, PR or deployment occurred.

1. Ask Aidan for explicit approval of the reviewed temporary counter-image comparison and planned restoration. The earlier automatic approval review rejected proposed programming under the no-reprogram restriction. The offline preparation is complete, so approval now concerns this concrete packet.
2. If authorised, SOL alone checks the current console and board state, then stages and performs the smoke checks and original-bitstream comparison. Preserve raw evidence. On healthy completion restore the original image and weights and verify the original BOS scores. Any abnormal state or lost acknowledgement is fail-stop, with separately reviewed recovery. Independently audit correctness, timings, module energy, resource changes and counter interpretation.
3. **Stop before roadmap step 4.** Decide the broader experiments and measurements with Aidan. No memory-placement, parallel-MAC, CPU feedback or scalar-arithmetic optimisation work yet.

## Physical-test approval received

On 15 November 2026, after the exact packet review, Aidan explicitly approved: “Yes, please go ahead with SOL. Temporarily load the counter circuit, run the reviewed comparison, then restore and verify the original circuit and weights. Stop before step 4.” This supersedes the earlier no-reprogram restriction for this test. SOL remains sole board operator, with fresh preflight and all existing fail-stop conditions. The frozen protocol and packet bytes remain unchanged. Physical results are pending.

## Completed physical comparison — current stopping point

[Findings](../results/observer-qualification-20261115T182057Z-11c575/findings.md), [run](../results/observer-qualification-20261115T182057Z-11c575/run.json) and [independent audit](../results/observer-qualification-20261115T182057Z-11c575/audit-manifest.json).

- SOL alone ran the approved packet after private login/sudo refresh. Console `6796.gradiated-kv260` was detached at completion. The same board boot was verified. The console-open-to-verified-staging observation was 386.9 seconds, inside the 540-second staging limit and outside inference/power measurements.
- Dispatch 18:47:12 UTC, final restoration verified 18:52:42 UTC. Controller exit 0. All 14 gates passed, covering 36 scored, 18 warm-up and three smoke requests, with 2,656,960 signed-score comparisons on the board. The Mac audited compact per-position receipts, not downloaded raw score arrays.
- Four planned firmware switches completed. Final original firmware `gradiated-tiny-50mhz.bit.bin` was operating with zero manager flags, original weights restored, and all 320 original BOS scores matched. The temporary installed observer file was removed. No further board command or experiment followed.
- Pairwise generation changes: −0.5190%, −0.0242%, −0.0115%. Gross VCC_SOM energy per completion: −0.5559%, +0.1287%, −0.3373%. These are one-boot module-rail observations, not general improvements or whole-board energy.
- Pair 1 `encoded-hello` median verified latency differed by −2.217%, outside the registered symmetric ±2% descriptive band. One original generation interval was 466.050 ms versus 442.138 ms for its replicate. This is generation variation, not the earlier verification-tail outlier. Cause unresolved. Research status is `inconclusive` for timing neutrality, with functional/counter/restoration acceptance explicitly true. Do not silently discard the metric or claim an observer speed-up.
- All six traces had 350 samples with no missed slots. The independent audit re-decoded all 14 UART gates and separately integrated all six traces across five alignment cases. Counter snapshots passed phase partition, token/score/cache geometry, idle stability and overflow checks. Core busy includes score-transfer waiting. Other event counters overlap phase totals.
- Raw directory: `.agents/runtime/hardware/inference/outputs/observer-qualification-20261115T182057Z-11c575/`. Sealed 237-artifact manifest SHA `49f7c84abade4f8c0be244c624bf68b15307aced0b39237bc6e6afeab27ce992`. Result SHA `becc26304df3e93852bfd31f16a0bc711377dc1fb4266f727b8b1370346e3c33`. Transport-observation SHA `2b323c482050b979fb7ac34de96a4cf89fc5f1754e8b3a85b58cd35064248581`. Separate audit directory uses the same run name with `-audit` appended. Preserve both and all original records.

Next: discuss the full step 4 experiment and measurement set with Aidan, including whether stronger observer qualification is necessary. Do not start extra repetitions, memory-placement, parallel-MAC, CPU-feedback or scalar-arithmetic experiments without that decision. No commit, push, PR or deployment occurred. The frozen protocol is retained byte-for-byte with its pre-run status. Current completion status lives here and in the result, rather than rewriting a protocol pinned by a completed run.
