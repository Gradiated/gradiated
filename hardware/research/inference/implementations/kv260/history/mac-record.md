# Gradiated FPGA tiny transformer

A deliberately overfitted chip-joke generator for learning, a Sand to Thought
blog post and Gradiated marketing. The project teaches genuine inference in the
KV260's programmable logic using
one 26,720-parameter transformer. The original model's later physical integration
is maintained by the server chat. The new actual-text candidate below runs on
the Mac and has not been deployed to the FPGA; older hardware sections record
the earlier Mac milestones.

## Current actual-text candidate

```sh
cd /Users/aidanmcconnell/.codex/worktrees/fpga-inference/gradiated
research/fpga-inference/generative.sh conditioned-chat
```

Type actual text, up to 48 UTF-8 bytes; Ctrl-D exits. The transformer receives every
input byte via a lossless encoding and greedily generates output tokens. No seed,
input hash, response ID or answer lookup. Same input repeats; each entry is a new
completion. It emits memorised chip jokes rather than answering questions.
Append `--format fixed` to use the W16A16 integer software reference on the Mac.
The selected fixed conversion balances one internal channel to retain the original
FPGA scales, including down weights at `2^-16`. It matches all 1,000 outputs of
the prior integer conversion; no new circuit operation is required. Server
equivalence/package checks are separate, and the physical test is deferred.

Both formats produced 991/1000 exact authored jokes across 40 jokes on the frozen
synthetic final set. Empty input and some Unicode/repetitive inputs still fail.
A supplementary 50-input usability screen gave 50 exact jokes across 16 jokes;
repetition remains noticeable. [Protocol, evidence and limitations](../model/conditioned.md)
and [candidate/payload pins](../model/conditioned.json). No board deployment occurred.

## Original BOS-only control

The commands and results in this section retain the earlier model unchanged.

From this isolated worktree:

```sh
cd /Users/aidanmcconnell/.codex/worktrees/fpga-inference/gradiated
research/fpga-inference/generative.sh chat
```

To try the software version using fixed-point calculations:

```sh
research/fpga-inference/generative.sh chat --format fixed
```

This opt-in mode runs integer neural arithmetic on the Mac CPU: 16-bit weights,
16-bit working values, 48-bit dot accumulators and integer nonlinear functions.
The default command above still uses the selected q8/FP32-intermediate MLX model.
Both use the same external FP64 token sampler. Neither runs on the FPGA yet.

Enter requests a joke with a fresh random seed. Text supplies a reproducible
sampling seed, not a question the model understands. `q` quits. Optional
`--seed 10001` makes blank entries use 10001, 10002, and so on.

Every request starts from one token. The model predicts every byte; the host
samples the first 32 bytes and then selects the most probable byte until EOS.
No joke identifier, answer lookup, output mask, retry or repeat filter. Repeats
and mistakes are displayed. [Model details and limitations](../model/README.md).

## What to open

| File or folder | Purpose |
| --- | --- |
| material/one-liners-review-v2.txt | Your editable joke wording, including newer drafts |
| material/character.md | Current desired identity and humour |
| material/joke-library.txt | Readable catalogue of 106 earlier banked joke versions |
| material/library.jsonl | Preserved dialogues, prompts, draft material and historical notes |
| model/jokes.json | Exact frozen 48-joke training snapshot |
| model/selection.json | Original architecture, recipe and FP32/q8 payload hashes |
| model/fixed.json | Accepted fixed-point arithmetic, payload pin, regression hashes and real projection trace |
| tools/model.py | Original network, byte sampling, optimizer and numerical checks |
| tools/fixed.py | Integer forward calculation, calibration, comparison and fixed-point sampler interface |
| tools/generative.py | Chat, verification, RTL simulation and explicit training commands |
| tools/rtl.py | Pinned simulator setup, independent fixtures and observed-trace checks |
| rtl/mac32.sv | Reused 32-term MAC with one-row, Q-only or Q/K/V projection control |
| rtl/mac32_tb.sv | Arithmetic, reset and handshake testbench |
| rtl/qk_rope.sv / qk_rope_tb.sv | Serial Q/K positional rotation and its testbench |
| rtl/kv_cache.sv / kv_cache_tb.sv | Append-only K/V memories, visibility/read control and tests |
| rtl/cache_viewer.html | Observed cache writes, addresses, reads and reset walkthrough |
| rtl/rope_viewer.html | Observed pair-rotation teaching-page template |
| rtl/viewer.html | Offline teaching-page template, populated from real simulation traces |
| rtl/toolchain.json | Isolated simulator version, source and checksum pins |
| tools/runtime.py | Offline sandbox, environment pins and watchdog |
| tools/llama_numpy_reference.py | Independent arithmetic reference |
| hardware.md | Proposed PL engine, numerical formats, memory budget and acceptance gates |
| learning.md | Current explanations and teaching route |
| history.md | Earlier findings and recovery instructions |

The historical library preserves 2,749 unique records, with provenance for 227
input documents and inert earlier source snippets. It includes withdrawn drafts
and former identities; those are historical material, not current instructions.
[Material guide](../material/README.md).

## Verify or reproduce

```sh
research/fpga-inference/check.sh
research/fpga-inference/generative.sh verify
```

The first command runs DevEx, syntax and focused model/material/security tests.
The second verifies the original FP32/q8 formats, reproduces all 128 pre-cleanup
token sequences exactly, checks NumPy/cache/packing and performs one fresh-model
optimizer update. It also verifies 128 frozen fixed-point token hashes, primitive
integer oracles and the pinned real projection trace. It preserves the known gibberish case rather than filtering it.
The original result is 127/128 exact authored jokes across 41 different jokes;
all 48 jokes are training data, so this is not an unseen-language test.

Explicit future reproduction only:

```sh
research/fpga-inference/generative.sh train
```

This trains fresh random weights with the fixed 2,000-pass recipe and writes a
new FP32/q8 export to ignored runtime output. It never replaces selected weights.
No additional full training run was performed for cleanup.

## Linux build host and private desktop

The user-provisioned Netcup RS 4000 runs Ubuntu 22.04.5 x86-64 with about 32 GB
RAM and a 503 GiB root filesystem. Its Tailscale name is `fpga-build`
(address `100.73.61.0`). A fresh Tailscale SSH login as the user-created
`admin` account succeeded, including Tailscale's additional authentication
check. The 1.104.5 Tailscale version was observed on the server. These are host
checks, not FPGA or Vivado results. No model weights have been uploaded.

`desktop-setup.sh` prepares Xfce plus Ubuntu-packaged xrdp on this host.
It is separate from the pinned offline Mac model environment. It refuses other
OS/architecture combinations and requires an existing, tested Tailscale SSH
connection. Run the reviewed copy in the server terminal:

```sh
sudo bash /home/admin/fpga-build-setup/desktop-setup.sh admin
```

The script has a 20-minute timeout and installation lock. It temporarily prevents
the RDP services from auto-starting before configuration, preserves original
configuration under `/var/lib/gradiated-fpga-desktop/`, then permits only
localhost RDP (`127.0.0.1:3389`) and session-management (3350) listeners.
The session manager may use IPv4 `127.0.0.1`, IPv6 `::1`, or both; each is
loopback only. Wildcard and other addresses are rejected. It requires TLS,
disallows root desktop login and drive redirection, and disconnects idle sessions
after 15 minutes without intentionally killing disconnected sessions. Upstream
limits on idle detection still apply. It records installed package versions and
a root-only setup log at `/var/log/gradiated-fpga-desktop-setup.log`.
Failure after service masking leaves desktop services stopped/masked for review.

After checking the desktop listeners, it masks/stops the standard OpenSSH
service and socket. Tailscale runs its own SSH server, so a new private login
must be verified after this step. Netcup SCP's **Screen** remains the recovery
console if Tailscale access fails; repair Tailscale there rather than opening
public administrative ports. Do not disable MFA, broaden company access rules,
copy passwords into scripts or make RDP public.

Once setup succeeds, open a **second Mac terminal** and keep this running:

```sh
tailscale ssh admin@100.73.61.0 -N -o ExitOnForwardFailure=yes -L 127.0.0.1:13389:127.0.0.1:3389
```

In Microsoft Windows App, add a PC named `127.0.0.1:13389`, friendly name
`FPGA build`, using the Linux account/password entered locally. A self-signed
RDP certificate warning must be checked against the certificate/fingerprint
obtained through authenticated SSH. Keep local-folder redirection disabled.
Closing the tunnel stops desktop access; it does not terminate server builds.
The RDP password is never needed by the agent.

Current status: all 49 project checks passed. The embedded editor also passed
on the actual Ubuntu xrdp 0.9.17-2ubuntu3.1 package while preserving its 15
repeated Xorg arguments. The first privileged run installed packages, then
stopped/masked desktop services because its checker incorrectly rejected IPv6
loopback `[::1]:3350`. The corrected checker accepts this session-manager
address and checks TCP connectivity to every permitted desktop listener.
The corrected sudo run completed. Fresh private SSH passed afterwards, with
OpenSSH service/socket masked and no kernel TCP port-22 listener. Observed
listeners are `127.0.0.1:3389` and `[::1]:3350`; both desktop services are active.
A temporary Mac localhost tunnel negotiated RDP TLS 1.2 and its SHA256 certificate
matched the one read through authenticated SSH; no login credentials were sent.
Direct IPv4 connections to public ports 22/3350/3389 and Tailscale ports 3350/3389
were refused. The test tunnel was closed. Installed versions are Xfce 4.16,
xrdp 0.9.17-2ubuntu3.1 and xorgxrdp 1:0.2.17-1build1. Aidan confirmed a successful Windows App desktop login. Xorg, xfce4-session and
xfwm4 were observed running as admin; 479 GiB of disk space remained. No browser
is installed on the server. The 2025.2 Linux web
installer was downloaded on the Mac, copied over Tailscale SSH to
`/home/admin/fpga-build-setup/vivado-2025.2/`, and unpacked there with
`--noexec --nox11 --target installer`. No installation or AMD login was started by the agent. The user later launched
xsetup; its GUI failed because libXtst.so.6 was still missing.

Verified file: `FPGAs_AdaptiveSoCs_Unified_SDI_2025.2_1114_2157_Lin64.bin`,
363,538,224 bytes, SHA256
`a78dbe8943c1c7ea14aea13937192d6316c0ba94e05bf6f4ebcdca9ef1a73280`.
Both AMD's signed digest and detached signature passed with the public key linked
on the [official download page](https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools/2025-2.html).
The HTTPS-fetched key's primary fingerprint is
`4D27DDF2A08955CE241B4304FD3DD2C355D2B701`, signing subkey
`E5F24BD454F2C46DB4D669A55DB253CE971AD24F`. GPG uses the separate
`verification-keyring` beneath that staging directory, without global trust
changes. Metadata and binaries stay outside Git; Mac installer was not executed.
Recheck in the server staging directory with `sha256sum` and:

```sh
gpg --homedir verification-keyring --batch --verify FPGAs_AdaptiveSoCs_Unified_SDI_2025.2_1114_2157_Lin64.bin.sig FPGAs_AdaptiveSoCs_Unified_SDI_2025.2_1114_2157_Lin64.bin
```

Measured: the bundled Java GUI requires missing `libXtst.so.6`; its JVM is
bundled and resolves with the JRE library paths. AMD's Ubuntu requirement also
calls for missing `libtinfo.so.5`. Both packages are available from the configured
Ubuntu repositories. The user must enter the sudo password locally to install
them; then launch the installer as admin from a terminal inside the Linux desktop:

```sh
sudo apt-get install --no-install-recommends libtinfo5 libxtst6
bash ~/fpga-build-setup/vivado-2025.2/installer/xsetup
```

AMD account credentials remain user-entered. Keep the pinned 2025.2/Kria ML
Standard route in hardware.md. Select only the needed tool/device families,
review the license terms and installation size with the user, and install into
an admin-owned directory without spaces. No root installer, SFD, Lab Edition,
Vitis AI/DPU or all-device download is needed for the current RTL work.

Sources: [Ubuntu xrdp configuration](https://manpages.ubuntu.com/manpages/jammy/man5/xrdp.ini.5.html),
[session management](https://manpages.ubuntu.com/manpages/jammy/man5/sesman.ini.5.html),
[Tailscale SSH](https://tailscale.com/docs/features/tailscale-ssh).


### Codex running independently on the build server

Current status: ChatGPT sign-in and the bounded real-agent disconnect test passed.
See the measured result at the end of this file. Earlier notes retain their
chronological state. The agent is currently idle.

Aidan requires the agent to keep working with the Mac closed, not merely remote
build commands launched by the Mac app. The Mac-hosted chat has not moved.
Codex CLI 0.166.0 was installed as admin using the inspected official standalone
installer from `https://chatgpt.com/codex/install.sh`, invoked non-interactively
with `--release 0.166.0` and a 180-second process bound. Installer SHA256:
`44ac252c1b9a68c02bdf0de8e1c6cbfde36fc1afa8684624962eae7d4c461e70`.
The installer verified archive digests, used ~/.codex/packages/standalone,
created ~/.local/bin/codex, and added that directory to ~/.bashrc. No sudo,
Node/npm, copied Mac authentication, model task or API-key spending was involved.
`codex --version` passed; `codex login status` returned not logged in.

The server already has tmux. A unique temporary tmux session started a synthetic
Python process, then the first SSH connection closed. A new SSH connection
observed the process's delayed marker and live tmux session. The probe session
and marker were removed. This demonstrates terminal persistence, not yet an
authenticated Codex task surviving disconnection. Reboot persistence is not set up.

User sign-in is next, from a server terminal:

```sh
tmux new-session -A -s fpga-codex -c /home/admin/projects/gradiated
~/.local/bin/codex login --device-auth
```

Complete the supported ChatGPT/workspace authentication privately, without
sharing codes, credentials or auth.json. If company settings disallow device
login, retain them and use a supported browser callback flow. Before agent work,
use the matching source checkout at `/home/admin/projects/gradiated` on branch
`codex/fpga-inference`. It is a shallow copy of this branch with the user joke
edit preserved as uncommitted, not a copy of the Mac environment or ignored
weights. Transfer provenance and hashes belong in ignored runtime. Origin
remains offline and pushes are disabled until GitHub access is arranged. Never
rely on a live Mac filesystem mount for server work. Use workspace sandboxing and normal approvals; do not run
Codex as root or enable approval/sandbox bypass. A task may stop on completion,
limits, error or a necessary approval; persistent terminal is not indefinite
autonomy. Keep builds/scripts on the server and use Vivado GUI for inspection.

After private login succeeds, launch from the project root inside tmux:

```sh
~/.local/bin/codex -C /home/admin/projects/gradiated --sandbox workspace-write --ask-for-approval on-request
```

The first task is a bounded, read-only project/Vivado readiness inventory.
Read root and FPGA AGENTS, run the root startup checks, preserve the existing
joke edit and report the tool versions. The FPGA Mac checks are unavailable
on Linux until a separate Linux-specific verification path exists; do not copy
or install MLX/the Mac virtual environment. Keep synthesis and new circuit
work for a subsequent authorised step. To detach tmux, press Ctrl+B, release,
then D; reconnect using `tmux attach -t fpga-codex`. Closing RDP is a disconnect,
not a Linux logout. Do not log out, stop the server or close the agent session
when leaving a task running.

Recommendation: CLI plus tmux for this Ubuntu 22.04 host. The official Linux
app is a preview supporting Ubuntu 24.04/26.04, not 22.04; Computer Use is not
available in that preview. Do not upgrade/reinstall this Vivado host just to add
the desktop agent. Sources: [Linux app](https://learn.chatgpt.com/docs/linux/linux-app),
[Codex CLI](https://learn.chatgpt.com/docs/codex/cli),
[authentication](https://learn.chatgpt.com/docs/auth).


## Local environment and weights

The pinned environment remains at `.agents/runtime/fpga-inference/venv/`, with
its Python distribution under `.agents/runtime/fpga-inference/python/`.
Dependencies are declared in pyproject.toml and pinned by uv.lock; no global
installation is used. Selected payloads are local SafeTensors under:

- `.agents/runtime/fpga-inference/models/tiny/q8/`: 36,310-byte weight file.
- `.agents/runtime/fpga-inference/models/tiny/fp32/`: 107,983-byte weight file.

An additional converted payload is under models/tiny/fixed/: a 64,648-byte
SafeTensors file containing 53,440 weight bytes and fixed coefficient tables.
It is pinned by model/fixed.json, along with its arithmetic source digest.

Original configurations and SHA256 hashes are retained. Weights/environments and
runtime logs are ignored by Git. The selected weights are not distributed by
cloning this repository; preserve these local copies. An exact original training
implementation remains at the recovery checkpoint for provenance.

Workers verify environment versions before loading libraries, strip credentials
and startup-injection variables, deny network and source/model writes, and have
absolute timeouts. Allowed writes are limited to runtime outputs/cache/tmp.
Normal account read access remains: this is not a hostile-file isolation boundary.

## Fixed-point comparison and next step

The selected teaching format uses **16-bit weights and stored working values**.
The matched 128-seed comparison produced 127 exact authored jokes across 42 jokes,
with one shared gibberish case (20003). 127 complete token sequences matched q8;
seed 20087 selected a different complete joke. No observed overflow/saturation.
This is a finite trained-joke test, not an unseen-language or universal-equivalence claim.

The maximum score difference remains .10922515, so the original .1 absolute
numerical limit still fails. Aidan selected 16-bit storage for teaching; the
explicit teaching policy keeps normalized RMSE <= .01 (measured .00555848),
primitive/cache checks, zero saturation and the original output-quality gates.
The earlier 18-bit result remains in Git/runtime history.
[Measured results and numerical limits](../model/README.md#fixed-point-software-study).

Reproduce the selected comparison, or the original strict negative result:

```sh
research/fpga-inference/generative.sh fixed --acceptance teaching
research/fpga-inference/generative.sh fixed --acceptance strict
```

To reproduce the earlier wider comparison, use `fixed --activation-bits 18`.
These reuse examined seeds as regressions, not new holdouts. Each full study
has a 1,200-second watchdog and writes payloads/results/source snapshots under
ignored runtime outputs; it never replaces selected weights.

The complete Q, K and V linear projections are now implemented and simulated; see below.
The full-model analytical reservation remains 47 RAMB36 sites. There is no
synthesis, physical fit, FPGA timing or energy measurement yet. Further board
work, cloud spending and publication remain outside the current scope.


## Q, K and V projections: simulate and explore

```sh
research/fpga-inference/generative.sh rtl
```

This compiles SystemVerilog with the checksum-pinned local Verilator 5.052,
then runs **55 full 96-output requests: 5,280 outputs and 168,960 products/partial
sums**, all checked exactly. The suite includes seven real model inputs, directed
rounding/clipping/extrema, identity/reversed-identity and random matrices,
busy requests, per-row stalls, invalid loading rows, memory reuse and eight reset
probes, including the Q→K and K→V boundaries. Every real model Q/K/V output also
matches the complete pinned integer reference at seven token positions. Input
normalization is still prepared in Python; positional rotation, caching, attention
and other layers are not RTL.

The first real Q vector begins `[-115, -5711, 2007, 3393, ...]`. One shared
multiplier and accumulator in the RTL visit all 96 rows: Q at 0..31, K at 32..63,
and V at 64..95. The first K and V outputs are -774 and 1053. Q/K integers use
scale 2^-11 and V uses 2^-12, so raw numbers across these banks are not directly
comparable. All three projections use the same 15-bit rounding shift.
The input memory is reused, the sum clears between outputs, and each tagged
result is streamed to the receiver. No output vector memory or DSP-count/fit
claim is implied. Simulator warnings remain fatal.

The earlier examples remain available. Q-only checks 1,696 outputs / 54,272
terms; single-output mode checks 156 outputs / 4,992 terms:

```sh
research/fpga-inference/generative.sh rtl --rtl-rows 32
research/fpga-inference/generative.sh rtl --rtl-rows 1
```

The command prints the absolute path of **projection.html**. Open that file in
your browser to step through the real simulation, see the circuit teaching
diagram, choose Q/K/V, jump between outputs, inspect each row’s 32 products and
view control waveforms. A grid shows the selected projection’s 32 outputs as
they are produced. The page is self-contained, has no remote assets and stays local. The diagram is an authored
view of the RTL architecture, not a tool-generated synthesized schematic.
Automated browser preview of local files was blocked by browser security policy;
data/control logic was checked offline, but rendered layout has not been verified.
Raw **waves.vcd** and **cycles.csv** are beside it; all generated files stay ignored.

The simulator lives under ignored runtime/toolchains, with no global installation
or Python dependency change. To provision the same pinned public bottle after
moving to a compatible Apple Silicon Mac, explicitly run:

```sh
research/fpga-inference/generative.sh rtl-setup
```

Setup has a 180-second deadline. Simulation is a separate offline/write-restricted
worker with a 180-second watchdog. The current native build uses existing Apple
Clang 21 and MacOSX26.5.sdk explicitly; it does not install an SDK. Compiler and
SDK metadata are recorded in results. See [hardware.md](../hardware.md) for ports,
schedule, controls and remaining work. RoPE is the next verified block below.
The cache is verified below too; attention and connecting the blocks remain later work.


## RoPE: rotate one Q/K pair

```sh
research/fpga-inference/generative.sh rtl-rope
```

This simulates a **separate positional-rotation block** with the existing pinned
simulator, sandbox and 180-second watchdog. It prints a local **rope.html** path.
Open it to choose token position, Q/K, head and pair, then play the observed
calculation or press **Show completed pair**. The diagram treats two coordinates
as an arrow; its observed rounded output appears after the four products finish.
Position 1 is the default, since position 0 leaves the input unchanged.

For each 16-coordinate head, pair 0 with 8, 1 with 9, and so on. Q and K each
have two heads; V is not rotated. One multiplier in this block sequentially forms
`a*c`, `b*s`, `b*c`, `a*s`; combine as `a*c - b*s`, `b*c + a*s`, round each once
by dividing by 16,384, and clip to signed16. Q/K input/output units remain 2^-11.
Coefficients come from the original pinned Q14 table. This block is not yet wired
to the projection circuit, so it does not share that block's physical multiplier.

**423 complete requests passed: 27,072 output values and 54,144 products/combined
values**, including nine reset probes, input/table conflicts, invalid positions,
busy writes and output stalls. Full-model comparisons cover 448 values from
seven authored prefixes plus 16,384 values across a synthetic 256-position
sequence. All match exactly with no clipping on those model probes. Synthetic
arithmetic tests deliberately exercise clipping. Each pair takes six simulated
edges after start; actual FPGA clock speed remains unknown.

All neural arithmetic shown here is RTL simulation. Python prepares Q/K and
loads the coefficient table. KV-cache storage is a separate verified block below;
attention and full-model circuit integration remain future work. Like the
projection page, the self-contained view uses no remote assets; its data/controls are checked offline, while rendered
layout remains unverified under the existing browser restriction. Logs, HTML,
VCD and CSV are ignored runtime artifacts. No new packages or downloads.


## KV cache: store and read a token's numbers

```sh
research/fpga-inference/generative.sh rtl-cache
```

This runs the separate **32 KiB logical KV cache** and prints a local **cache.html**
path. Open it and press **Next complete token**: a row changes from partly written
to readable only after its 32nd K/V coordinate pair arrives. Choose the full-cache
example to inspect any position/coordinate, or the reset example to see retained
RAM bits become invalid. The diagram follows the actual observed operation;
the location selector separately inspects recorded contents and word addresses.

K is stored **after RoPE**, with units 2^-11; V keeps units 2^-12. Each of two
memories has 256×32 signed16 words. Position p, coordinate c maps to word `p*32+c`
in both memories. The combined 64 values per token occupy 128 bytes. Reset clears
validity and counters without clearing all RAM words. The controller refuses
reads of unwritten/partial tokens, out-of-order writes, invalid addresses and
additional appends after 256 complete tokens. Reads return a registered pair,
held stable until accepted; only one read response may be outstanding.

The suite checked **113,624 clocks and 54,024 returned values exactly**, including
three full readback sweeps (49,152 values), 13 reset edges and backpressure.
The model fixture covers every one of its 16,384 Krot/V cache values, using an
explicitly synthetic repeated 256-token sequence. Two further fixtures exercise
address patterns, extrema and seeded random data. Full/incremental Python cache
layout and existing model regressions pass. Offline controls checks inspect all
16,384 displayed model values, partial/full/reset visibility and address selection.

This remains a separate RTL building block. Python supplies its Krot/V inputs;
projection/RoPE wiring and attention remain future work. Logical storage is not
a synthesized BRAM allocation or measured timing/energy result. The local page
replays observed traces; its rendered layout is unverified under the existing
browser restriction. No dependency, download, training or physical board work.


### Completed Vivado installation and remaining OS prerequisites

Aidan completed the GUI installation at `/home/admin/amd/2025.2/Vivado`.
Direct SSH checks observed `vivado -version` exit 0 with version 2025.2,
SW build 6299465. A bounded Tcl startup/device-inventory check (no synthesis,
project compilation or bitstream) returned both `xck26-sfvc784-2LV-c` and
`xck26-sfvc784-2LVI-i`, exit 0. Its script/output stay in the server's ignored
runtime `vivado-install-check-k8tqo0ok`. This verifies startup and device files,
not a finished FPGA design or an exhaustive dependency check.

The installer requests its Ubuntu OS prerequisite script. The inspected script
at `/home/admin/amd/2025.2/Vivado/scripts/installLibs.sh` has SHA256
`f216082924e30f9bc8a5b8e8058a8e69efbcf30861688057f0d1e9d374968cdc`.
Its Ubuntu branch runs apt-get update/install for runtime/GUI libraries and
build tools, including some shared Vitis/AIE prerequisites. It does not buy a
license. It writes a chmod-777 log in the current directory, so run it inside
the existing private (0700) setup directory. The user enters sudo locally:

```sh
cd ~/fpga-build-setup
sudo timeout --foreground --kill-after=30s 20m bash -e -o pipefail /home/admin/amd/2025.2/Vivado/scripts/installLibs.sh
```

The wrapper adds fail-fast pipeline checking and a 20-minute bound. The script
has not yet been run. Verify its completion/package state afterwards. Close the
optional License Manager; ML Standard 2025.2 needs no FLEX license key for Kria.
The screenshot's desktop-entry helper reports zero errors and skipped entries;
actual shortcut launch remains separate from the passing direct startup check.

Server source transfer passed all 3,216 tracked path checks, Git connectivity,
root startup checks and the preserved joke-edit hash. The server has no Git
remote and push.default=nothing. Codex login status now confirms ChatGPT login.
The persistent fpga-codex terminal exists. A synthetic native Codex sandbox test
passed workspace writes, denied outside writes (Linux EROFS) and denied direct
network access. For CLI 0.166.0 the diagnostic syntax is `codex sandbox -P :workspace`;
there is no linux subcommand. The authenticated agent test has NOT run: automatic
approval review rejected it because private project instructions/check outputs
would go to OpenAI without payload-specific user permission. A reviewed prompt
is prepared in the Mac's ignored runtime server-source-sync/readiness-prompt.txt.
The user must explicitly approve that payload and destination before retrying;
installation screenshots and successful account login are not that approval.


OS prerequisite completion: the user finished the package setup. All 19 Ubuntu
packages named in the inspected script are installed; dpkg --audit is empty and
no apt/dpkg/needrestart process remains. Vivado -version still passes. Tailscaled,
xrdp and xrdp-sesman are active and enabled for boot; systemctl --failed is empty.
Restarts were deferred in needrestart to preserve the RDP session. A controlled
reboot is now appropriate and was accepted by the user; it has not yet occurred.
Only an idle bash pane exists in fpga-codex, so no Codex task is being interrupted.
The tmux session does not survive a reboot and must be recreated afterwards.
After user-run sudo reboot, verify a new boot ID and fresh private SSH/RDP before
claiming recovery. The Mac RDP tunnel must be restarted if its SSH session exits.
The authenticated Codex test remains unrun and still needs the explicit payload/
destination approval requested earlier. Package/reboot progress is not that approval.


### Post-reboot checks and AMD updater autostart

Reboot recovery is now observed: boot ID changed, private SSH passed, the user
returned to the RDP desktop, tailscaled/xrdp/xrdp-sesman are active/enabled,
OpenSSH remains masked, dpkg audit is empty and no systemd units are failed.
Vivado 2025.2 still starts. Codex ChatGPT authentication and the exact uncommitted
joke edit survived. The idle fpga-codex tmux session was recreated; no Codex agent
was started. The earlier payload/destination approval remains pending.

A new wildcard TCP listener appeared after desktop login: Java PID 1282, class
com.xilinx.xic.XIC, executable under /home/admin/amd/xic. Public IPv4 TCP 44209
was reachable. This is the installed InformationCenter update helper; there is
no evidence of compromise or of an FPGA build running. Its user autostart entry
was /home/admin/.config/autostart/Xilinx Information Center.desktop, launching
/home/admin/amd/xic/xic -c -t. Added Hidden=true atomically and gracefully stopped
only that verified admin-owned helper. The original desktop entry is preserved
at /home/admin/fpga-build-setup/Xilinx-Information-Center-autostart.before.desktop.
No Vivado binaries or licenses were changed. The helper exited, TCP 44209 now
refuses public connections, and Vivado -version passed again. Public 22 and 3389
also refused connections. Manual InformationCenter launch may recreate its
listener; leave its automatic startup disabled and review update tooling before
using it. No further reboot was needed for this per-user autostart change.


### Approved bounded server-agent check

On 3 November 2026 Aidan explicitly approved the explained transfer to OpenAI
through the server's ChatGPT sign-in: root/FPGA instructions, only Linux build-host/
server-Codex README notes, and read-only readiness outputs. Earlier approval-pending
notes are historical and superseded for this one task. Secrets, weights, unrelated
source and joke contents remain excluded. The first real agent task is limited to
180 seconds, read-only, with a separate SSH connection checking after launch.
Installation, synthesis and ongoing agent work are outside this test.


### Measured server-agent disconnect result

The approved single task completed with exit code 0 in 60.17 seconds using
Codex CLI 0.166.0, read-only sandboxing and a 180-second outer timeout. The
launching SSH connection ended after dispatch into fpga-codex. Fresh SSH
connections observed the live task about 27 and 52 seconds after start, then
retrieved its completed result. Root startup passed, Vivado executable paths
were found without execution, and only the original joke edit remained dirty
with its expected SHA256. No build, install, synthesis or model ran. The nested
version check warned that read-only storage prevented PATH-alias creation but
returned the correct version.

The agent listed live Vivado validation and separate-SSH confirmation as
outstanding because those checks were outside its view. Parent checks already
verified Vivado 2025.2/K26 support and now observed SSH-disconnect persistence.
The claimed eight-second wait lacks a separate sleep event; independent SSH
observations provide the evidence. Logs remain in ignored server directory
.agents/runtime/fpga-inference/server-codex-readiness-9v_k0ckl.

The task is finished; fpga-codex retains an idle shell. From the Mac, inspect it:

```sh
/usr/local/bin/tailscale ssh admin@100.73.61.0
tmux attach -t fpga-codex
```

Detach with Ctrl+B, release, then D. The one-task approval is consumed; no
further task was launched. This proves independence from the launching SSH
connection, not server-reboot persistence or unlimited autonomy.
