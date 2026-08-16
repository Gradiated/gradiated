# Research log

Opened by the 2026-07-16 director after the fixed top-2/no-shared source implementation reached a terminal pre-request GPU exception. The current shared launcher already wires the source-bound exit-35 mode, so this project begins with the one direct candidate arm rather than integration or readiness work.

The inherited phase/runtime evidence remains under `../sequence_early_exit_architecture/`. Treat the `669.459` output tok/s all-exit ceiling as synthetic nomination evidence only. The measured decision is complete cache-off 8K/1K c16 execution at or above `594.466` output tok/s, with the r3 `552.171055` c16 point used only as current-identity context.

## 2026-07-16 — terminal external-systemd direct arm: operational null

Question/action: run the admitted candidate-only source-bound exit-35 AWQ c16 arm under direct `systemd-run --user --wait --collect` ownership, `RuntimeMaxSec=3300s`, and the pinned 8K/1K c16 geometry. Grouped mutable evidence was zero Nebius instances/disks; launcher, remote script, patch, checkpoint manifest, and experiment spec matched their pinned SHA-256 values. The first no-provider attempt exposed a malformed local tokenizer argument; the checkpoint itself contains the three required tokenizer files, so one immediate command-only correction used that admitted directory. It created no provider resource. The corrected direct owner then reached the provider-create phase and failed in 0.523 seconds with return code 3.

Evidence: `artifacts/nebius_l40s_exit35_c16_2026-07-16-r1/provider-create-diagnostic.json` (SHA-256 `d994a18a…`) retains the redacted Nebius response: `UserData is invalid`, specifically generated cloud-init YAML line 10. `events.jsonl` (SHA-256 `61e57962…`) records the stock identity, create-phase failure, and cleanup; `summary.json` (SHA-256 `35452fba…`) records 0.916 allocation-seconds, `$0.000218268` derived exposure, null useful GPU seconds, and final zero instances/zero disks. The independent final authenticated inventory also returned zero instances and disks.

Interpretation/next move: this is an `OPERATIONAL_NULL`, not an exit-35 result. No allocation reached a GPU, so there is no load, phase, semantic-divergence, request, telemetry, or throughput evidence and no conclusion about the `594.466` tok/s gate. The one-arm project is closed with no retry; a later separately admitted effort may repair the shared cloud-init/key binding.
