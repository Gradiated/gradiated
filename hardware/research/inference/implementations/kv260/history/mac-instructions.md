# FPGA tiny-transformer project

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


## Actual-text candidate (authorised 9 November 2026)

Aidan explicitly authorised improving the tiny transformer to receive actual
arbitrary text and emit an authored joke, with occasional gibberish acceptable.
This supersedes the earlier no-training/BOS-only scope for this new candidate.
Read model/conditioned.md and model/conditioned.json. Same26,720-parameter geometry;
lossless two-hex-symbol input encoding,48 UTF8 bytes max, no answer marker,
argmax over all 320 logits, no input seed/hash/IDs/answer lookup or retries.
Training targets use a last-byte relation, not semantic understanding. Final
FP32 and W16A16 each 991/1000 exact/40 distinct, mostly synthetic ASCII inputs.
999/1000 matched sequences, zero observed clipping. Empty/Unicode/repetitive
inputs can fail; identical inputs repeat. Full results and weights are ignored.

Run generative.sh conditioned-chat (Mac FP32) or append --format fixed (Mac
integer). Original chat/selection.json/fixed.json remain historical controls.
Preserve the human-edited material/one-liners-review-v2.txt byte-for-byte. The
new candidate uses the frozen original 48 targets, not that untrained edit.
All new workers retain 180s limits, isolated pinned environment, offline sandbox
and restricted writes. No installations/downloads or physical-board changes.
Old hardware-status sections above describe earlier milestones; consult the
server chat for current board state. This new candidate has NOT been deployed.
Its down weight exponent is -15 instead of the original -16, so hardware shifts
and exported payloads must be checked before any board load. Scope here is
local model work and scoped commits only; no push/PR or server overwrite.


## Original-scale conditioned deployment preparation (9 November 2026)

Aidan authorised deploying the actual-text candidate, then deferred the physical
board test. Mac selector now pins balanced conversion 20261109T190531255188:
up row 51 times 9/8 and down column 51 times 8/9 before quantization; all original
exponents retained, down -16 / SHIFT15. No retraining or clipped weights. Five
numerical probes pass normalized .01 teaching gate (max .00490673); absolute
.10631943 still exceeds historical strict .1. All 1,000 matched integer outputs
unchanged,991 exact / 40 distinct. Clipping-only alternative failed and is retained.
Read the latest conditioned.md section; earlier down-15 instructions describe
the retained initial conversion. Server has verified new weights and 522-position
full-state goldens; it owns RTL/native checks and offline package preparation.
No fresh Vivado build is expected if equivalence passes. Do not touch the board
until Aidan resumes that test. Preserve original models and the human joke edit.
