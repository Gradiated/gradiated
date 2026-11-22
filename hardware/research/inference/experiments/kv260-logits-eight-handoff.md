# Eight versus four final token-score lanes

Status, 16 November 2026: experiment 7 complete. Exact simulation, the routed build, the physical four-versus-eight-lane comparison and independent audits passed. Original circuit and weights are restored and verified. The first serial transfer attempt was preserved as aborted before dispatch. The clean retry succeeded after terminal recovery and temporary Mac sleep inhibition. At Aidan's request, the board's ubuntu sudo inactivity timeout is now 24 hours, retaining password and terminal scope. Aidan subsequently adopted logits-8-lanes-v1 as the selected baseline. Stop here and discuss any next experiment with Aidan. No commit, push, deployment or article-prose change was made.

## Question and prior evidence

Does doubling the four-lane final projection to eight lanes improve complete-request speed and module energy enough to justify its added resources? Experiment 6 established exact scoring, 3,040 projection clocks with four lanes and routed 50 MHz timing. Its four-lane whole requests use 7,922,865 / 11,778,637 / 20,625,187 clocks for Hello / six-byte / max48. The complete circuit uses 34,795 LUTs, 13,367 registers, 33 DSPs and 38 block RAM tiles. Four projection DSPs read four banks of two RAMB36E2 each.

The mechanism is eight independent output-row accumulations fed by eight distinct weight banks and one broadcast activation. Logical weights and arithmetic order remain unchanged. Score outputs retain the serial handshake. Competing explanations include memory-bank packing, added routing/fan-out, output handshakes, host delivery variation and other transformer phases. More parallel circuitry may offset time savings in power. First falsifier: exact component and seven-case matched RTL replay must establish predicted projection-only cycle savings before a routed build.

## Frozen analytical prediction

A group takes one priming clock, 32 accumulation clocks, one rounding clock and L score handshakes. `(34 + L) × (320 / L)` gives 3,040 clocks for four lanes and 1,680 for eight, saving 1,360 clocks per scored position. At 50 MHz, first-output production should be 0.0272 ms earlier. Predicted whole-request savings are 123,760 / 167,280 / 142,800 clocks, or about 1.56% / 1.42% / 0.69%. No saving is expected in other model phases. Eight projection DSPs imply 37 total if other mapping is unchanged. LUT, register and BRAM mapping require actual implementation reports. Energy direction is unknown. These are predictions, not observations. All seven case predictions are pinned in the coordinator runtime.

## Fixed controls and measurements

Keep the exact four-lane source and programming image from experiment 6, frozen chip-joke-text-20261109 W16A16 model, 50 MHz target, three historical prompts, scores, rounding/clipping, output IDs/stops/cache, host observer and power boundary. Give the eight-lane variant a new source identity and preserve previous sources and immutable records. Reuse the four-lane build without rebuilding it, but replay both RTL arms and rerun a matched physical control.

Follow measurement standard v2's core scorecard: exact correctness, output counts, CPU-visible TTFT/decode TPS/completion time, internal cycle attribution, active/idle module power, gross joules per answer/output token and tokens/J, resource counts/percentages, memory mapping and available operating conditions. Use three AB/BA/AB block pairs, three warm-ups and six timed requests per arm per pair as in experiment 6. Report spread and small or inconclusive differences, without rerunning until a preferred result appears. Record all 34 coverage families with missing or reused evidence explicit. VCC_SOM is module energy, not whole-board or FPGA-only energy.

## Execution and restoration

SOL is sole Linux/board owner. Design and source admission precede simulation/build, exact simulation and routed timing precede physical dispatch, and the coordinator independently reviews each result. Freeze stage-specific source hashes, absolute deadlines and bounded recovery before execution. Reuse existing tools, simulator and Linux host without creating a new reservation. Copy unique builds, images and raw evidence to checksum-verified Mac storage. Shared independent backup remains pending.

Aidan's request authorises temporary loading of the reviewed four- and eight-lane circuits and restoration and verification of the original research circuit and pinned weights, including 320 original BOS scores. The old no-reprogram restriction was explicitly withdrawn. Requalify current boot, console owner, source pins and privilege before dispatch. The latest verified original-state reference is experiment 6's final restoration SHA-256 `41503b0cce9962226d0ed6772ec4c3a51973f39bcc9c68bba1ad87fe5baa5dae`. Do not infer current live state from this historical pin alone. Keep current safety/timeout gates. No Ethernet setup, commit, push, deployment or automatic adoption.

## Ownership and preservation

Checkout `/Users/aidanmcconnell/dev/gradiated-hardware-wip`, branch `hardware/research-and-articles-wip`, starting HEAD `8f67839f3643dfdb89c554e4bafab6d9d3f0ba72`. Initial hashes cover 4,189 existing files at `.agents/runtime/hardware/inference/outputs/logits-eight-v1-coordinator/initial-files.json`. Concurrent article, figure, lecture and website-test edits belong to other work and must remain untouched.

SOL chat `01a1301d-6afb-7053-b238-354703c4cb49` owns new variant/tests/protocol/results and sole live execution. Coordinator chat `01a1d0ea-a381-7050-8265-ff2310b83101` owns this handoff, indexes, private article progress and independent audits. Flag a shared private-plan edit before writing. Stop after this comparison and discuss further experiments with Aidan.

## Completed simulation and build admission

Both arms passed exact retained scores, output IDs/stops and valid KV contents for all seven cases. Both component result widths passed products, ordered sums, rounding/clipping, loader, stalls and reset cancellation. The archived four-lane replay matched exactly, and only the final scoring phase changed. All seven independent cycle predictions passed. Matched result SHA-256 `f17783bf33787972479a07ebc2fd08c56e96d8bf6466a60a0608be8d35ce3256`.

The admitted eight-lane generated transformer SHA-256 is `dc5851764926a6b5e3638aea760eb025d86da844241497a175e125c6210d0e2d`, differing from the saved four-lane transformer only in the lane parameter. All other ten generated modules are identical. Build archive SHA-256 `e3d5e6fbd1813cd3145815541892ae92eac359b3af93690810c191be48dcae6e`, manifest SHA-256 `dc7fe72d2ce600d35424f70d977c92fab4936f4bae8412d1db2d1bef0045bd9d`. All 18 members and required support-name/checksum changes passed independent review. Physical results remain pending.

The first harness launch stopped before compilation because its new Python module name shadowed a legacy helper. The failed attempt is preserved. Renaming the new helper to materialise_eight.py and its caller import fixed the collision. RTL, fixtures and protocol did not change, and the corrected harness was independently readmitted before simulation.

## Routed build and current physical preparation

All 318 recovered build files passed independent hash and archive verification, along with admitted source closure, all seven bounded phases, complete route/clock/timing coverage, zero DRC errors/critical warnings and programming-image conversion. The circuit meets 50 MHz with +2.747 ns setup and +0.011 ns hold slack. Totals are 35,188 LUTs, 13,689 registers, 37 DSPs and 38 BRAM tiles, adding 393 LUTs, 322 registers and four DSPs over four lanes. Each of eight weight banks maps to one RAMB36E2, keeping total block RAM unchanged. The shared activation-memory primitive mapping is unchanged.

Recovered build archive SHA-256 `3645855efd4a5c952f6af0b8c17d7cd294f87a421da8050400a73e3568dceee3`, programming image `bdc134c65a151699d2ddd690b0ddc799cbd09edb688b8a7c4f0ecf7dd498c9e2`, overlay `a1bc5ea2bdbb02d29b1d9759da24be67594f9d0033c40483cfd47828cc16b1a7`.

The current dedicated console is `89057.gradiated-kv260`. Aidan confirmed private login and sudo returned 0, asking SOL to detach the console. The admitted fresh-capture invocation SHA-256 is `1bfe69acc80a0564285bdeb31a7c7d33ad19066e2ef344cf3f3e373af13dd095`. Current-state review and physical packet admission remain required before dispatch. Do not substitute historical console names.

## Admitted physical run

Packet `logits-8-lanes-20261116T193809Z-a9fdf0` passed independent review. Invocation SHA-256 `b2d57dada9dbbb6accd20d38188c677cb271d87033cf3417b97b03fc5922ba85`, transfer SHA-256 `e34e5a5d4d8c4db166c9c9fcc9e594b4a3dea6dfae16e1fc6329cc9b00d8d698`. All 35 source pins, 23 payload members, 15 lifecycle stages, four/eight image roles and unchanged workload and measurement code were checked. Independently decoded fresh state SHA-256 `48a27b589e995b41e3a6938b815f7dd1738a434c403f95914a7cbef5096e7902`, serial archive `32d8afbb2fb2b998a0960575c89b38c8651a51f0b826858b05bd134cd9fc8efb`, matches the latest experiment 6 original-state restoration on the same boot with no new kernel notices. The run is authorised to proceed under the existing timeouts and restore and verify the original circuit and weights. Results and final restoration remain pending.

## Transport interruption and bounded recovery

The first physical packet stopped before dispatch with `UART archive flow-control marker missing` and `launch_dispatched: false`. No staged, dispatch-intent, physical gate or result receipt exists. Serial receipt SHA-256 `8c93629de5df7c2fca2fdeff222ad7ccf6a6bc918abc707a4dbc2866a66964ef`. SOL identified Mac idle sleep from 19:51:09 to 19:57:29 UTC, exceeding the receiver's timeout. Preserve this aborted attempt separately, including the small relevant power-log excerpt. It contributes no inference timing or energy observations.

A clean retry is authorised within the existing experiment scope after current-state requalification and independent admission of a fresh tag/packet. Images, workload, measurements and restoration remain unchanged. Wrap the bounded Mac runner in `/usr/bin/caffeinate -i -s` for its lifetime to prevent automatic idle sleep, without permanent Mac settings. Keep the laptop lid open. The console remains `89057.gradiated-kv260`, but the subsequent probe reports `SUDO_REQUIRED`. Aidan has been asked to renew privately and confirm 0. Do not treat the earlier confirmation as a new renewal.

### Console recovery before retry

After the transfer timeout, Aidan reported that typing was invisible. SOL confirmed an attached idle shell, then detached the specific console with logging off and cleared partial input. A harmless tagged probe showed `ixon ixoff icanon -echo`. SOL changed only `stty echo`, verified `ixon ixoff icanon echo`, a second marker and an idle Kria prompt. No password was read or entered, no FPGA operation ran and no measurement condition changed. The user has been given the reattach command and asked to renew sudo privately. Await the actual renewed 0 confirmation before proceeding. Timeout termination can bypass the receiver's Python finally block, so future failed UART cleanup should check terminal echo as well as receiver/process state.

## Verified sudo setting and admitted retry

Aidan subsequently confirmed a fresh sudo result of 0 and requested a 24-hour interval. On 16 November, SOL installed only `/etc/sudoers.d/99-gradiated-ubuntu-timestamp`, containing `Defaults:ubuntu timestamp_timeout=1440`, owned by root:root with mode 0440. The prior setting was 15 minutes. Standalone and whole-policy visudo checks, the effective Ubuntu setting and unchanged base sudoers bytes passed. Password authentication and existing tty scope remain unchanged. This is a sliding 24-hour inactivity timeout on the same terminal, not a promise that reboots or different consoles avoid authentication. No password was stored. The command initially stopped before mutation because a long wrapped shell prompt failed the idle check. SOL verified the expected prompt, cleared partial input and changed the shell working directory to /home/ubuntu before the successful apply.

Verified sudo receipt SHA-256 `134c4163714588f6d21c8c81ecb56ea0ae87c73f17ddf7e9c728369a51426378`, admitted invocation `2f2c40a7038eaba10638a7a3f449efabe8ec87941c87f85e11491936b4c5cdfb`. The scripts and receipt are preserved in the coordinator runtime. To reverse this setting, first confirm that the named drop-in still contains exactly our single line, then remove only that file with sudo and run `sudo visudo -c`. Other sudo policy must remain untouched.

Fresh retry capture SHA-256 `520b520c05c7d6b23123c14e6a25be4380ca83027e90ae00c5ff6287d7c15f43`, serial archive `19cd94e903cff914b5b33653297520dcb96ae1241af0ec1044d89b9f74aa3f5a`, independently matches the original state on boot `305f2b01-e9fd-4461-8e6d-0cf91979d151` with no new notices. Retry packet `logits-8-lanes-20261116T202250Z-44df9d` passed independent source, image-role, schedule, transfer and lifecycle review. Invocation SHA-256 `06340ed7c83556e17047ea9308a833ab94892d36a432a50a174440e4b117b5bb`, transfer `742c0937c8f7614084dad1ba1e85f0481cddfb30c173a5fb9c43f188268196d6`. The exact same experiment is admitted with process-bound caffeinate and final original-state restoration. New audit receipts use retry-prefixed names and preserve the failed first attempt. Physical results remain pending.

## Completed physical comparison and independent audit

The successful retry ran 36 timed requests and 18 warm-ups across three AB/BA/AB pairs. All 15 gates passed. The coordinator independently decoded every gate, reproduced raw CPU timing and six 350-sample module-power traces under five alignment assumptions, and reconciled all 34 metric definitions, 180 numeric samples and 34 coverage families. All 18 paired first/last/completion counter differences match the exact RTL prediction. SOL also checked all 36 absolute per-request counter triplets against the correct simulation arm. The original circuit and pinned weights were restored, with all 320 original BOS scores matching. This does not claim full weight-memory readback.

| Prompt | CPU-visible TTFT, ms (four → eight) | Decode tokens/s | Completion, ms |
| --- | ---: | ---: | ---: |
| Hello | 11.879 → 11.851 | 614.9 → 625.3 | 158.711 → 156.235 |
| Six-byte prompt | 14.104 → 14.091 | 551.9 → 560.3 | 235.814 → 232.483 |
| 48-byte prompt | 145.715 → 145.693 | 389.9 → 394.1 | 413.004 → 410.152 |

Rows are medians over six timed requests per arm and prompt. One useful output token is one byte for this frozen model. Exact internal first-output production improves by 1,360 clocks, or 0.0272 ms. CPU-visible differences include delivery and scheduling variation. Complete-request cycle savings are 1.56%, 1.42% and 0.69% respectively.

Gross VCC_SOM energy per answer averages 0.844436 → 0.836783 J and per output token 0.00801680 → 0.00794414 J. Paired midpoint energy changes are −1.047%, −1.013% and −0.658%. All fifteen alignment comparisons remain lower, spanning −1.051% to −0.631%. Mean active module power is 3.12879 → 3.13379 W. The observed saving comes from the shorter measured block despite slightly higher power. This small one-boot result is not a calibrated sensor-accuracy bound or a claim about whole-board or FPGA-only energy. The energy window includes inter-request gaps and final verification.

The net whole-design resource increase is 393 LUTs, 322 registers and four DSPs, with the same 38 BRAM tiles. The scoring hierarchy itself rises from 672 to 1,131 LUTs (+459), because the tool also remaps surrounding logic. Do not label the whole-design LUT difference as a direct count of added lane circuitry. Eight banks each occupy one RAMB36E2 instead of four banks each occupying two. The stored weights are unchanged. Projection execution is 1.81× as fast, but the remainder of inference and serial score handshakes limit the whole-request benefit.

Result SHA-256 `09a45b365c3290e66a5817cf41eedab50a42eb9e5a66c5c2254b6b2750cbc099`, compact run `8f826df934aa6940ef839638682300aae8aa49b8777474f01fe741b553bab536`, final original-state `cce97a59285f6ca0803826c09e0ad2eef0d0e6d792540520fe9d7458f85721a4`. Final independent receipts are `physical-audit.json`, `physical-counters.json` and `record-check.json` in the coordinator runtime. The final console is detached and process-bound Mac sleep inhibition has ended. Unique raw evidence and build images are retained in verified Mac storage. Shared independent backup remains pending.

[Physical findings](../results/logits-8-lanes-20261116T202250Z-44df9d/findings.md) · [Run record](../results/logits-8-lanes-20261116T202250Z-44df9d/run.json). Scalar-div-v1 remains selected, and four lanes remains the explicit experimental control for this comparison. No further circuit experiment or baseline adoption is authorised by the result alone.

## Subsequent baseline adoption

Aidan adopted **`logits-8-lanes-v1`** as the selected circuit comparison baseline on 16 November 2026, after experiment 7. This supersedes scalar-div-v1 as the starting point for new experiments. Earlier versions, result records and their dated selection statements remain historical evidence. Adoption does not change the circuit currently loaded on the board or authorise new experiments. [Exact source, image and software pins](../implementations/kv260/README.md#selected-circuit-comparison-baseline). The four-lane version remains the historical experimental control for experiment 7. Earlier paragraphs describe the selection status at completion, before this adoption.
