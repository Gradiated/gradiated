# FPGA tiny-transformer project

## Balanced conditioned candidate ready; board test deferred (9 November 2026)

Aidan explicitly chose to leave the new model's physical test for later.
Server-only validation/package preparation is complete; do not program, open
MMIO, change clocks/network/QSPI or start a physical test until he asks. The Mac
FPGA BUILDER chat retains physical ownership. Existing physical acceptance below
belongs to the earlier BOS-trained weights, not this conditioned candidate.

The new weights retain all original exponents and shift 15 after an offline
up row51 times9/8 / down column51 times8/9 balance. No training or RTL/bitstream
rebuild. Mac numerical probes max normalized RMSE .0049067316 <= .01; zero
weight clipping/observed activation saturation. The previously examined 1000-input
format regression matches all prior integer sequences, with 991 exact/40 jokes,
largest 85 and all EOS. Keep empty/Unicode failures, repeats and the limitation
that input-ending associations do not establish semantic understanding.

Verified 30-file input transfer is ignored conditioned-balanced-import-20261109,
manifest SHA256 c0d3b73943ab580199cc7a4ceb0807c9a215e250d58c169fab016b019598a4fc.
Fresh model-compare-l9bvejs9 accepts all seven cases (522 inputs), 895800 integer
state/cache comparisons, 169280 scores including seven BOS clear replays,
plus independent observed-stage arithmetic. All 24 tool calls cleaned up within
180-second watchdogs; longest simulation 149.78s. Native six-suite ASan/UBSan
mock validation and 125 offline tests pass. README pins all reports/provenance.

Sealed conditioned-6wbein7j package manifest SHA256
b0394ba256d877fb62d6eb6e74942d5ff0c649cf751d53481e827c8bae5e9167;
archive SHA256 567d0a1499c7bf1dbb45e3814d74a2f052989ac973a32cc5efabc2697e892509.
Original bitstream, ARM library and three overlays are reused exactly. Do not
modify this or older sealed packages in place. The pinned package profile binds
new model/reference identities, exact high/low nibble input encoding (48 UTF8
bytes, BOS, no answer marker), greedy all 320 decisions and default cap 255.
Original byte-prefix packages keep their existing protocol. Every line resets
and loads a fresh session; no history, mask, seed, retries or neural CPU fallback.
CLI seed generation is rejected for the conditioned profile. Physical execution
of these new weights remains unverified; existing 50 MHz timing is reused for the
unchanged circuit, with no new physical performance/energy claim.

## Physical inference and audited generation passed (9 November 2026)

The physical KV260 now executes the selected transformer. After initial BOS and
first16 smokes, all four original frozen prefix cases (1/16/128/256 tokens)
passed 128,320 exact signed32 score comparisons and three explicit context
clears. Six physical generations (47,20001,20002,20003,20087,20128) produced 517
positions and 165,440 recorded/integrity-checked scores. Every actual sampling
decision matched the original pinned Mac NumPy 2.5.4 worker. These generation
scores were checked for integrity/sampling, not independently compared with
fresh neural-reference scores. All five previously frozen fixed-token hashes
matched, including known gibberish seed20003; 47 is an extra audited sample.
Five outputs are exact distinct authored jokes; all six reached EOS with valid
UTF8. Preserve the full known failure, no resampling or filtering. This is finite
regression evidence for a deliberately memorised 48-joke model, not held-out
language, conversation, novel humour, throughput, power or cost evidence.

All 35 transferred evidence files are verified under ignored
`board-bringup/mac-multitoken-generation-20261109/`; trusted manifest SHA256
`274800d29108d6cce19b7e91c3ab9f19eae06ee9da77775acc6f1378ed10ffef`.
README.md pins the summary/final-state hashes, results and bounded reproduction.
Every audit binds its hardware packet and every frame checksum/token/draw;
all six 180-second watchdogs exited zero and reaped their workers. No Mac neural
or optimiser calls. Original generation packets remain `sampling_verified:
false`; the accepted audit sidecars supply the subsequent verification.
The UART wrapper failed before seed20002 began; the retained file-existence
inventory shows no attempt/result for that seed. Correcting handoff timing
preceded its sole execution; no generated output was discarded.

Final captured state: three candidate overlays applied, manager operating,
flags0, taint0, PL0 kernel-reported enabled at 50 MHz, UIO4/FCLK/AFI bound,
DFX runtime-inactive but boot-enabled, Ethernet carrier0. Stock-file hashes and
QSPI revision reports match the recovered baseline; last reported context105.
This is runtime state with no auto-load boot service. Keep the clock enabled;
the Mac owns physical operations. No further hardware work is needed this turn.
The initial kernel fault below is historical, before clean recovery and the
successful corrected firmware-file load; do not present it as current failure.

New sealed `bos-h50in0kf` extends the native adapter/runner only, reusing
unchanged `host.c`, aligned 32-bit MMIO and DSB barriers. Each explicit session
starts with reset/full model load; token steps retain KV, explicit clear retains
weights, closing only releases userspace resources. Every native call has a
30-second budget and each extended CLI mode has an absolute 180-second child
watchdog (configurable 1..600). No retries, automatic recovery or neural CPU
fallback. Preserve the known limitation that userspace cannot rescue a hung
hardware bus transaction.

`--validate J01-first16`, `--validate all` and the six `--generate` cases above
have passed physically. The package contains all four frozen references through
256 positions. All 320
scores at every position are compared. Batch generation uses all vocabulary
entries, sealed original NumPy draws and stdlib FP64 sampling on Arm; it retains
every raw hardware frame; any NEW run remains explicitly UNVERIFIED until the
original pinned Mac worker audits every decision. A raw-score `--stream` API is also
available for exact external sampling. No seed retry, filtering or replacement
after a failed audit. README.md pins the manifest/full archive/five-file delta,
CLI and protocol. All six circuit/model/reference/overlay payloads shared with
the previous package are identical; all old packages remain sealed. Offline
checks pass: 27 board tests, 55 model-contract tests, six native host mock suites
with ASan/UBSan, and ARM barrier/access-width inspection. Physical acceptance is
now supported by the transferred receipts. The final evidence update changes
only README/AGENTS; no tests or implementation/hardware actions were repeated,
and the model, circuit, sealed packages and user joke edit remain unchanged.

## Historical first-load kernel fault (9 November 2026)

The corrected `bos-7ie8ziyp` package was verified on Mac/board. Its ARM library
loaded without MMIO, stock-app unload succeeded, and the separate FCLK overlay
bound with PL0 at 50,000,000 Hz and no new kernel errors. Exactly one programming
overlay attempt then triggered a Linux 6.8.0-1015-xilinx #16-Ubuntu BUG in
`sg_alloc_append_table_from_pages -> cma_heap_attach -> dma_buf_attach ->
fpga_mgr_load`. No interface overlay, AFI binding, model MMIO, weights or token
ran. Post-fault taint was 640; `operating`/empty status was stale state, not a
successful load. README.md pins the verified receipts and exact-source diagnosis.

The stock inspection already had manager flags `20` (hex, DMA-BUF mode).
The exact Ubuntu patch makes that global mode override an image's firmware name,
and leaves both the mode and buffer pointer after dropping its load reference.
Wrong-path selection is confirmed; reuse of freed buffer/page storage is the
leading inference, not a proved allocator-lifetime reconstruction. The previous
loading procedure omitted this inherited-mode gate. Keep existing sealed
packages, circuit and model unchanged. Aidan subsequently authorised the minimal
Python preflight guard and a fresh package: `inspect_board` now requires flags
parsed as hexadecimal zero, rejecting missing/malformed/nonzero data before
MMIO. Four added behavioral tests cover those cases on an otherwise-ready
synthetic board; all 14 board tests and 55 model-contract tests pass. This
postload inspection does not replace the manual flags-zero gate before loading.
New sealed `bos-ghzmrwrd` supersedes `bos-7ie8ziyp`; README.md pins its manifest,
full archive and 6,858-byte delta. Only its Python runner and manifest differ;
the other seven payloads are identical, including reset119 overlays/native
library/circuit/model. Old packages were fully rehashed and preserved. Apply
the delta to a fresh copy of the verified predecessor, never the sealed original.

Human-controlled recovery is now verified by the separately hashed
`recovered-readonly.json` receipt pinned in README.md. Fresh boot ID
`bcb863cb-0211-48a8-a817-ab0c80dccd03`, taint zero, stock app/overlay/firmware
restored, stock file hashes and both QSPI slot revisions retained. Only the
original four performance-monitor UIOs remain; no candidate clock/AFI bindings.
PL0/PL1 are back at 99,999,999 Hz. Ethernet carrier is zero. Existing boot
diagnostics match the earlier baseline; do not describe it as an empty error log.
Stock loading again sets flags `20`; recovery does not close the mode gate.
No candidate retry, MMIO or inference followed recovery. No automatic retry,
reboot, overlay cleanup or loading on a tainted kernel. The next bounded
experiment must release stock ownership, exclude concurrent loaders, select
unencrypted full firmware-class mode with manager flags zero and verify zero immediately before
the programming overlay. Reverify the 50 MHz clock and all existing gates.
This avoids the stale DMA-BUF branch by source analysis; physical success is
unproven. Do not merely change the overlay or firmware filename and retry.

## Reset correction before first physical load

The reset-116 BOS package `bos-4w4hau6h` is withdrawn from deployment; preserve
its sealed bytes. Exact generated wiring uses `pl_resetn0 -> EMIO95`, whereas
published firmware ID116 maps to EMIO92 and ID119 maps to EMIO95. The corrected
program/AFI overlays use 119. Package preparation now pins and joins the actual
generated HDL/XCI to installed firmware definitions; tests reject the old ID,
changed wiring and incompatible geometry. Live preflight also checks both
reset properties against controller identity/ID119 before any MMIO. README.md
pins the guarded `bos-ghzmrwrd` package and retained reset-only predecessor
`bos-7ie8ziyp`, with unchanged circuit/weights/library and tests.

The Mac chat owns physical board operations under Aidan's explicit first-load,
BOS/multi-token/generation scope; the server remains the implementation owner
and observer until a runner extension is requested. No installs, training,
QSPI changes or network connection. Do not rebuild/alter a sealed package in
place. A full responsive stock restoration is not specified: AFI writes are
not undone by overlay removal, and stock DTBO has no AFI/clock restoration.
Keep the clock enabled on failure and leave power-cycle/normal-boot fallback
to the user; no automatic retry, reprogramming or reboot.

## Current board bring-up

The initial KV260 inspection found correct power and a responsive console. On
9 November Aidan authorised wiping only the microSD; the Mac chat installed
official Kria Ubuntu 24.04, verified full readback and supervised private login
setup. It preserved QSPI and kept Ethernet unplugged. Sealed original reports
and complete live DT/loading/UIO captures are transferred to ignored
`board-inspection/mac-ubuntu-24.04/`; README.md pins their manifests. The board
reports KV260 revision 2, Linux 6.8 and boot firmware 01.02. Existing UIO devices
are performance monitors, not our model. Initial PL0 was ~100 MHz; the first-load
clock stage later passed at 50 MHz before the kernel fault described above.

`tools/board_prepare.py` prepares an offline first-BOS package with the exact
sealed bitstream/model/original scores, installed-tool ARM cross-compilation and
staged clock/program/AFI/UIO overlays. No new dependencies or models are installed.
`board_bos.py` defaults to file/sysfs-only inspection. Its explicit --run-bos
mode is a device-writing test, not a read-only probe. No clock/AFI changes,
candidate loading or MMIO test follow merely from the read-only inspection
authorization. Read the README's staged procedure and close its remaining
driver/physical-compatibility gates before acting on the board. Kernel-reported
clock status is not an oscilloscope measurement; offline overlay resolution and
ARM cross-compilation are not physical execution proof.

The subsequent read-only driver check passes: CONFIG_XILINX_FCLK=y and
CONFIG_XILINX_AFI_FPGA=y, both expected drivers registered but no candidate
devices bound. README.md pins the transferred receipt. No installation or
modprobe is needed. Keep the sealed existing BOS package intact; physical
clock setup subsequently passed, candidate programming failed in the kernel,
and AFI/interface setup and the one-BOS comparison remain unexecuted. A staged
load must explicitly cover those writes; do not infer their success from this
registration check.

## Latest continued hardware scope

Aidan has now asked the server chat to start the remaining hardware process and
get as far as possible: implement missing transformer calculations, connect and
verify them, progress through Vivado synthesis/implementation and programming-file
preparation when the design is ready, then board testing when the physical
connection is available. This extends the earlier simulation-only restrictions
below. Do not claim full-model, synthesized-fit or board milestones from partial
tests. No new dependencies, downloads, training, paid resources, push or PR.
Scoped local commits remain authorised. The physical KV260 must have no internet
access; initial board inspection/programming remains dependent on a local cable
and inspection of its existing image/firmware. Preserve all host security controls.

Selected weights and minimal archived RTL fixture bundles have since been
transferred from the Mac and their existing hashes reverified. They are under
ignored runtime models/tiny and mac-frozen. Exact trusted bundle identities and
replay instructions are in README.md and tools/rtl.py. Keep the Mac environment
on the Mac; loading verified tensor bytes for hardware fixtures is not permission
to recreate its MLX environment or bypass the model worker. Original/fixed full
software generation regressions still require that original environment.

Fresh original Mac whole-model references are now transferred and verified.
`--vivado model-compare` passes four prescribed inputs (1/16/128/256 tokens),
all 21 returned integer states, every causal logit and accepted K/V write:
709,492 values including four clear-context replays. This is numerical proof
for those teacher-forced cases, not new language-quality or physical-board proof.
The complete offline PS/AXI candidate may now generate IP outputs (180 seconds),
synthesize (600 seconds) and run separate opt/place/route (600 seconds each),
with two threads and 180-second reports. Require the accepted sealed numerical
gate, actual compiled-source closure and sealed predecessor checkpoint chain.
Never waive DRC or invent clocks to clear warnings. Physical board software/
firmware compatibility is still unverified; no flashing, reboot or programming
is authorized by the read-only USB inspection.

An offline candidate `.bit` may be prepared after the accepted complete
PS/AXI/neural routed timing/clock/DRC report, under a separate 180-second tool
watchdog. This is file preparation only. It does not initialize the actual PS,
verify its software/address/clock configuration, contain runtime model weights,
or authorize loading/flashing from the read-only inspection. Keep the image and
model package ignored and label their target/required PS configuration explicitly.

The current server work is split into disjoint scalar/RMSNorm, dense/feed-forward,
and connected frontend/attention work. Parent owns shared harness/docs. Keep all
generated files under ignored runtime with 180-second simulator invocations.

The continued scope now includes a core-only OOC placement/routing diagnostic
while the fresh Mac whole-model export is prepared. Use the verified synthesis
checkpoint, provisional 10 ns clock, two threads, explicit maximum 600-second
opt/place/route stages and 180-second reports. Reject combinational-loop and
other critical warnings; never waive DRC to obtain a passing result. This does
not release numerical or board acceptance gates. A pinned installed KV260
PS/AXI candidate may be logically validated offline; its clock/address/reset
choices still require comparison with the physical board's image/firmware.
No programming file, hardware-manager operation or physical measurement follows
from a core diagnostic alone. Long-context simulation may omit VCD, retaining
all numerical CSV events and the same 180-second wall watchdog.

Follow the root AGENTS.md and Aidan's latest instructions. Work only in the
`codex/fpga-inference` worktree on the Mac, or the authorised matching server
checkout at `/home/admin/projects/gradiated` on branch `codex/fpga-inference`.
Another chat owns the original Mac article checkout. On the server, limit edits
to research/fpga-inference and ignored runtime; do not work on product/website code.

## Start here

1. Run `python3 tools/devex/start.py` from the repository root.
2. Check Git status and preserve user edits.
3. Read README.md, model/README.md and material/character.md.
4. On the Mac, run `research/fpga-inference/check.sh`; after model/runtime changes
   also run `research/fpga-inference/generative.sh verify`. These use the pinned
   Mac/MLX runtime, which must not be copied to Linux or recreated by installing
   substitutes. On Linux, run the root startup checks, inspect installed Vivado
   and simulator versions, and run scope-appropriate RTL/Vivado checks once the
   tool is installed. Report unavailable Mac-only checks explicitly.

## Current scope

Aidan authorised cleanup to focus on the new 26,720-parameter BOS-only transformer.
Old experiments/code are recoverable at local Git tag
`codex/fpga-experiments-before-cleanup` (commit e164e1958). Their obsolete local
weights are retired; Git does not contain those weights. Historical source
material is preserved in material/library.jsonl with provenance/index, not loaded
as instructions, current training, user approval or evaluation evidence.
Do not restore the old experiment tree unless asked.

Current model: one Llama-style block, width 32, two 16-wide query/key/value heads,
SwiGLU 128, vocabulary 320, tied embeddings, context 256. All 48 jokes are trained.
Inference sees only BOS 256; host samples all 320 logits at temperature .8 for the
first 32 bytes and then uses argmax. No IDs, reply lookup, masks, retries, rejection
or repeat filter. Text input only hashes to an RNG seed; it is not understood.

Eight-bit affine group-32 matrices with FP32 metadata/norms/intermediates/KV cache;
not an integer FPGA format. Retain selected q8 and FP32 weights under ignored
`.agents/runtime/fpga-inference/models/tiny/`. Verify their model/selection.json
hashes before loading; use local SafeTensors only, no pickle or remote code.
The isolated Python, exact installed-version check, clean environment, network
and source/model-write restrictions and absolute worker watchdog are required.
No new dependencies, model download or unrestricted runtime bypass.

Registered model result: 127/128 exact authored jokes across 41 distinct jokes;
seed 10125 is gibberish, repeats occur. Cleanup regression must match every one
of the original 128 token sequences, including that failure. Also verify FP32/q8
NumPy logits/cache/packing and the retained real training-step smoke. Reserved
seeds are not held-out language situations. No conversation, novel humour,
no-repeat, uniform sampling or perfect coherence claim.

## Creative material and changes

Preserve the original material text files and user wording exactly. The current
editable review is material/one-liners-review-v2.txt, including newer uncommitted
J39 wording; it is separate from the trained model/jokes.json snapshot.
Historical/withdrawn drafts are preserved but do not override character.md.
Do not train or silently incorporate edits during cleanup or verification.
`train` is an explicit opt-in reproduction command writing a fresh ignored export;
it does not change selected weights. Future training needs task authorisation.

## Hardware, teaching and repository boundaries

Full inference is Mac software. The KV260 is disconnected. The full Q/K/V
projection RTL (96 outputs), RoPE and KV-cache blocks have been simulated
separately on the Mac; no synthesis, bitstream, physical fit or measured FPGA energy/timing result exists. Current
RTL scope is below. Distinguish PL arithmetic, Arm CPU work and
external host work, including token sampling. Specify widths, signedness,
rounding and overflow before implementing integer arithmetic. Compare with the
independent NumPy reference before making performance claims.

Weight tensors plus full 256-position FP32 cache are analytically 99,200 bytes
before buffers/packing; not synthesized fit. Preserve the teaching goal and
honest deliberate memorisation. Another chat owns the article prose/visuals.
Keep routine output/weights under ignored runtime; useful decisions/code/prompts
belong here. No cloud, physical board work, push or PR is authorised by this cleanup.
Local scoped commits are authorised; exclude unrelated user edits.


## Selected fixed-point teaching format

Aidan chose 16-bit weights and stored activations/KV on 2 November 2026.
`model/fixed.json` pins the converted integer weights/tables, static exponents,
implementation digest, 128 token hashes and real 32-term projection. The opt-in
`generative.sh chat --format fixed` uses this Mac integer reference; original
q8 remains the default. Keep 48-bit dot accumulators, declared 32-bit scores/
logits and checked 64-bit nonlinear scratch; do not claim every number is 16-bit.
The 128-output matched check gave 127 exact jokes, 42 distinct, one shared
q8 gibberish case and one different complete joke. Zero observed saturation.
The original absolute-logit .1 gate still fails at .10922515. Explicit teaching
acceptance retains normalized RMSE <= .01, output gates and arithmetic checks.
`fixed --acceptance teaching` reproduces selection; default strict mode reports
the known numerical failure without confirmation. Earlier W16A18 history is
preserved. This original scope was later extended to the first RTL block below;
no further training or physical board work is authorised.


## First RTL block (authorised 2 November 2026)

`generative.sh rtl --rtl-rows 1` compiles/simulates rtl/mac32.sv and rtl/mac32_tb.sv in the
existing offline/write-restricted worker. 16-bit operands, 32-bit products,
48-bit sum, shift 15 with ties-even rounding/clipping. Two 32x16 memories retain
data through synchronous reset. Check every one of 32 trace terms against the
independent Python/Fraction oracle. Current suite: 150 vectors + six replays,
4,992 terms, five reset probes; real first-Q sum -3,760,136 -> -115.
`rtl-setup` is an explicit network-capable provisioning command only for the
pinned public Verilator 5.052 bottle; it changes ignored runtime/toolchains,
not the global environment or pinned Python packages. Both setup and simulation
are bounded to 180 seconds. Preserve the simulator's tree hash and strict lint.
Use existing direct Apple compiler/SDK paths as recorded, not xcrun defaults.
Source/tool pins and viewer template are tracked; build, VCD/CSV/HTML and logs
are ignored. Keep authored teaching diagrams distinct from synthesized circuit
views. Local-file browser automation was blocked; offline JS/data checks passed,
rendered layout is unverified. No synthesis/board/full-layer result is implied.


## Full Q projection (authorised 2 November 2026)

The earlier `generative.sh rtl --rtl-rows 32` runs 32 rows, reusing the same 16x16
multiplier/48-bit accumulator and shift-15 rounding. It loads one shared input
vector and the complete 32x32 weights; input memory is written only with row zero.
Each output carries a row tag and remains stable until accepted; only the last
accepted output returns idle. Reset cancels the matrix and resets its row index,
retaining memories. Results are streamed; no output-vector RAM is implemented.
Require all 32 values to match the pinned full integer model at seven real token
positions plus independent product/sum/rounding checks. Current matrix suite:
46 cases + seven replays = 53 matrices, 1,696 outputs, 54,272 terms and six reset
probes including later-row reset. Single-row regression via `--rtl-rows 1`
still gives 156 outputs and 4,992 terms. Seven token-position probes do not test
attention context; normalization/input preparation remain Python work.
The existing walkthrough now selects rows and shows all observed outputs.
No new tool/dependency/download, synthesis, board work, training, push or PR.


## Q/K/V projections (authorised 3 November 2026)

`generative.sh rtl` now defaults to 96 rows: Q 0..31, K 32..63, V 64..95.
One shared 32-value normalized input and one multiplier/48-bit accumulator serve
all three matrices. Preserve W16A16, signed 32-bit products, ties-even shift15
and output clipping. The pinned exponents imply the same shift for all banks:
Q/K sums 2^-26 → outputs 2^-11; V sums 2^-27 → outputs 2^-12. Validate that
relationship against the manifest; never compare differently scaled raw integers.

The 46-case suite plus nine replays passed 55 complete requests, 5,280 outputs,
168,960 terms and eight reset probes, including Q→K and K→V. All 672 real Q/K/V
coordinates at seven token positions match the pinned full integer model with
no clipping. All row addresses 96..127 are rejected. Q-only and scalar modes
remain regressions. The existing local walkthrough selects projection/output,
shows correct scales and only observed values. Offline JS/data controls passed;
rendered browser layout remains unverified under the existing browser restriction.

The trace checker retains one complete request at a time. Keep strict simulator
warnings, pinned tool/source hashes, offline/write restrictions and the 180s
watchdog. No output-vector RAM, normalization, RoPE, cache, attention, full-model
RTL, synthesis, board work, new dependencies/downloads, training, cloud, push or
PR is part of this milestone. Original model and editable joke material remain
unchanged; scoped local commits only.


## RoPE (authorised 3 November 2026)

`generative.sh rtl-rope` runs rtl/qk_rope.sv and qk_rope_tb.sv in the same pinned,
offline 180s worker. Source snapshots include both blocks and both viewer templates.
This is a separate block with one reused multiplier, not yet connected to mac32.
Python supplies Q/K and the pinned coefficient table. Pair j with j+8 in each
16-wide head; process Q's two heads then K's two heads (32 pairs, 64 outputs).
Four signed16×signed16 products per pair; signed48 combine, ties-even shift14,
signed16 clipping. Input/output exponent -11; cosine/sine exponent -14.

Idle-only input/table loading, a latched position (reject >=256 before narrowing),
tagged paired outputs and backpressure are explicit interfaces. Reset cancels
work and clears status/indices, retaining both memories. Original table is
loaded from the pinned payload; no on-device trigonometric calculation or new
learned weights. The 413-fixture suite plus ten replays gives 423 requests,
27,072 outputs, 54,144 products and nine reset probes, all exact. Full-model
comparisons cover seven authored prefixes plus all 256 positions of a synthetic
repeated training sequence (16,832 Qrot/Krot values, no clipping). This is not
new language or complete hardware attention evidence.

The local rope.html explains one pair with observed products/combined values,
a position/Q/K/head/pair selector and a two-dimensional arrow diagram. Default
position 1 shows a nontrivial rotation; position 0 is identity. Keep the prior
browser restriction and use offline data/control tests; rendering is unverified.
KV cache, attention, normalization, circuit integration, synthesis and board
execution remain later work. Same no-install/download/training/cloud/push/PR
boundaries and preservation rules apply; scoped local checkpoints only.


## KV cache (authorised 3 November 2026)

`generative.sh rtl-cache` runs rtl/kv_cache.sv and kv_cache_tb.sv through the same
pinned offline 180s worker. Separate K-after-RoPE/V signed16 memories each have
8192 words (logical total 32 KiB), units -11/-12. Address is position×32+coordinate.
Append positions in order and coordinates 0..31; commit a token only on its final
pair. Prior committed rows may be read between partial writes. No partial-row
visibility or overwrite of committed rows. Reject full count256, positions>=256,
coordinates>=32 and conflicting commands. Nine-bit position/count and six-bit
external coordinate prevent truncation before validation. Reads are synchronous,
one response outstanding, tagged and held under backpressure. Reset clears
validity, progress and response registers while retaining RAM bits.

The full suite checks 113,624 clocks / 54,024 returned values, three complete
8192-address sweeps (49,152 values), 13 reset edges, partial appends, full-cache
refusal and stalls. Model Krot/V equals the returned full cache and incremental
first-three-token cache; all 16,384 model values read back exactly. The 256-token
model context is synthetic repeated training material, not language evidence.
Two additional payloads use distinct patterns/extrema and seeded random values.
Independent Python protocol replay must check all readiness/events/metadata/data.
All 43 project tests and original/fixed model regression pass. No new Python file.

The local cache.html replays early writes, full-cache boundary reads and reset,
with a token/coordinate map and complete observed model readback. Diagram
addresses follow actual operations; selectors inspect recorded memory separately.
Keep offline control/data checks and the prior browser restriction; rendering
unverified. Cache, RoPE and projections remain separate; no attention, connected
inference, synthesis, board, install/download, training, cloud, push or PR scope.
Original payloads/user wording remain untouched; scoped local checkpoints only.


## Linux build-host setup (authorised 3 November 2026)

Aidan ordered one Netcup RS 4000 and requested guidance through Ubuntu, private
access, desktop and Vivado setup. This extends the earlier no-cloud boundary
only to this already ordered host; no additional spending, servers, policy
changes, push or PR are authorised. Ubuntu 22.04.5 x86-64 and Tailscale 1.104.5
are observed; private ping and fresh SSH as the user-created admin account
passed, including Tailscale's authentication check. No root password was shared.
The server source checkout is prepared below; weights, environments and
credentials remain outside the transfer.

desktop-setup.sh is host provisioning, separate from Mac model/runtime controls.
All 49 checks passed, including configuration ambiguity/symlink guards and
IPv4/IPv6 loopback versus exposed-listener regression checks. An actual
Ubuntu xrdp package probe preserved 15 repeated Xorg arguments; a temporary Mac
localhost tunnel was tested and closed. The staged server script hash matches.
The first sudo run installed desktop packages, then stopped/masked desktop
services because the original checker rejected IPv6 localhost [::1]:3350. The
checker now accepts IPv4/IPv6 loopback for sesman while requiring IPv4 loopback
for RDP; all other addresses remain rejected. The corrected sudo run completed.
Fresh Tailscale SSH passed after OpenSSH was masked/stopped. Both desktop
services are active; observed listeners are 127.0.0.1:3389 and [::1]:3350.
A temporary localhost tunnel negotiated RDP TLS 1.2 with a certificate SHA256
matching authenticated SSH; no desktop credentials were sent. Direct public
IPv4 ports 22/3350/3389 and Tailscale ports 3350/3389 refused connections. The
probe tunnel was closed. Aidan confirmed the Windows App desktop login; Xorg, xfce4-session and xfwm4
were observed running as admin. The host has 479 GiB free and no browser.
The user-downloaded Vivado 2025.2 Linux web installer is transferred and
unpacked in ~/fpga-build-setup/vivado-2025.2/installer. The user launched
xsetup, which failed on missing libXtst.so.6 before the GUI opened.
AMD signed digest and detached signature both verified in an isolated GPG
keyring; exact SHA256, key fingerprints and reproduction are in README.md.
The bundle's own extraction integrity check passed. No installer ran on macOS.
Missing Ubuntu packages libtinfo5 (AMD requirement) and libxtst6 (actual GUI
dependency) need user-entered sudo; then launch xsetup as admin inside the desktop.
Do not collect AMD credentials, accept licenses on the user's behalf, or install
extra products/device families. Vivado was subsequently installed; see the latest status below.
Keep RDP/session management on loopback through a Tailscale SSH tunnel; no public
RDP or MFA bypass. The user enters administrator credentials locally.
Netcup Screen is the recovery path. Preserve original configs,
record package versions, retain the 20-minute bound, and fail closed on desktop
configuration/listener errors. Vivado remains a later verification step; current RTL is still separate simulated blocks only.


Aidan clarified that Codex itself must run on the server while the Mac is off.
Official standalone Codex CLI 0.166.0 is installed non-root under admin's home;
its version/help passed, but it is not authenticated. Installer hashes/commands
are in README.md. Only the source checkout described below is authorised for transfer; no
weights, Mac environment or Mac credentials are part of it.
Existing tmux passed a synthetic process persistence test across separate SSH
connections; that isolated probe was cleaned up. Codex-task disconnect behaviour
still needs testing after user sign-in and project sync. Reboot recovery is not
configured. Keep normal sandbox/approval controls, no root agent or bypass flags.
Linux desktop app preview supports Ubuntu 24.04/26.04, not this 22.04 host, and
lacks Computer Use; CLI+tmux is recommended. This Mac chat has not moved hosts.
Aidan approved CLI+tmux and is installing Vivado separately in the Linux desktop,
with /home/admin/amd as the chosen install root. Source workspace setup is now
authorised. Prepare a shallow source-only clone of the current FPGA branch at
/home/admin/projects/gradiated, preserving the one uncommitted user joke edit.
Keep provenance/transfer hashes in ignored runtime, not new evidence reports.
Do not transfer .env, auth.json, keys, Mac venv, old model weights or browser data.
Keep the server's origin local/offline and pushes disabled until GitHub access
is explicitly arranged; never push or make a PR from this project scope.

The persistent tmux session is fpga-codex. Codex requires user-owned sign-in;
never collect or capture authentication links/codes/tokens. Use the regular
workspace-write sandbox with on-request approvals, not root or bypass flags.
Verify real workspace write, outside-write and direct-network boundaries before
agent work. The first authenticated task must only inventory this checkout and
Vivado readiness; no installation, synthesis, dependency change or model task.
A short bounded task in tmux should prove progress across separate SSH sessions.
This does not prove survival across server reboot or indefinite autonomous work.


Latest setup status: GUI installation completed at /home/admin/amd/2025.2/Vivado.
Direct -version and a bounded Tcl get_parts xck26* check passed: version 2025.2,
SW build 6299465, both commercial/industrial K26 part files present. No synthesis
or circuit compilation ran. The Ubuntu installLibs.sh is inspected but pending
user sudo; README records its hash, packages, private-log directory and bounded
fail-fast command. License Manager can close; no trial/key is needed for Standard.
Source transfer checked 3,216 paths, Git connectivity, preserved joke edit and
root startup. The persistent terminal exists; Codex ChatGPT sign-in succeeded.
Native sandbox synthetic boundary checks passed; actual authenticated agent
work remains untested. Automatic approval review blocked the bounded readiness
task because it would send private project instructions/notes/check output to
OpenAI. Do not retry or work around that block until the user explicitly approves
the exact payload and destination. The prepared prompt is in ignored Mac runtime.
The user's installation screenshots are progress information, not approval.


OS prerequisites subsequently completed: all 19 packages listed in installLibs.sh
are installed, dpkg audit is empty, no apt/dpkg/needrestart processes remain,
Vivado -version passes, no failed systemd units, and tailscaled/xrdp/xrdp-sesman
are active/enabled. User deferred service restarts and agreed to reboot if needed.
A reboot is now being recommended, not yet observed. Only the idle tmux bash
exists; no agent task ran. Recreate tmux after reboot and verify private access.
The Codex context-transfer approval requirement remains pending independently.


Post-reboot verification passed: changed boot ID, fresh private SSH, user RDP,
active/enabled Tailscale and desktop services, masked OpenSSH, clean dpkg audit,
no failed units, Vivado 2025.2 startup, retained ChatGPT login and preserved joke
edit hash. fpga-codex tmux was recreated idle; the authenticated agent task still
requires the previously requested explicit OpenAI payload/destination approval.

AMD InformationCenter autostart created a publicly reachable wildcard TCP 44209
listener after desktop login. The verified admin-owned Java XIC helper was
terminated gracefully and its user .desktop autostart entry now has Hidden=true.
Original entry is saved in ~/fpga-build-setup/Xilinx-Information-Center-autostart.before.desktop.
Public TCP 44209/3389/22 now refuse connections; Vivado startup passed after
closing XIC. Do not auto-launch InformationCenter, re-enable that entry or
silently reopen its listener. This was a measured exposure fixed during setup,
not evidence of compromise. Vivado itself remains installed and usable.


## Approved server Codex readiness test (3 November 2026)

Aidan explicitly approved the previously described OpenAI context transfer and
bounded server-agent test with “go ahead please”, after the payload, destination
and purpose were explained. This supersedes earlier approval-pending notes for
this one task only. Through the server's signed-in ChatGPT account, the task may
send root/FPGA AGENTS.md, the Linux build-host/server-Codex README sections and
read-only readiness outputs to OpenAI. Credentials, authentication files, weights,
unrelated source and joke contents are excluded. Do not read model/README.md or
material/character.md for this limited inventory, despite the general startup
list above. No installs, downloads, builds, synthesis, training, pushes or PRs.
Use one read-only task with a 180-second outer limit in tmux; verify progress or
completion through a separate SSH connection after the launching connection closes.
This approval does not grant ongoing unrestricted agent access or reboot persistence.


Approved readiness test completed successfully (3 November 2026): server Codex
0.166.0 ran read-only under a 180-second timeout and exited 0 after 60.17 seconds.
The launching SSH connection closed after tmux dispatch; fresh SSH connections
observed the task still running at about 27 and 52 seconds, then read its result.
Root startup passed, Vivado executable paths were found without execution, and
the original joke edit/hash remained unchanged. No build, install or model ran.
A nested CLI-version check warned about read-only PATH alias creation but passed.
The final answer claimed an eight-second wait without a separate sleep command
in the events; use independent SSH observations as persistence evidence instead.
The task finished; fpga-codex retains an idle shell. The one-task approval is
consumed. Ongoing tasks and server-reboot persistence are not authorised/proven.
