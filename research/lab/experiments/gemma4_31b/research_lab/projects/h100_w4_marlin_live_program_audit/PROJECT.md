# H100 W4-Marlin live-program interpretation audit

## Question

Do the immutable local bytes already captured by the live W4 owner's passing `PRECREATE_TERMINAL.json` actually implement the paid brief strongly enough that retrieved sentinel, sweep, profile, head-trigger, accounting, and cleanup artifacts may be interpreted?

Read only the frozen project files and pre-create artifact for run `gemma-h100-w4-marlin-20260717t17431784302994z`. Do not poll, wait for, message, edit, or otherwise influence the owner/service/provider. No provider access, GPU, image pull, or compilation.

Adversarially verify actual AWQ producer/pack/repack/Marlin calls, varied-sign nontrivial dual oracle, exact shapes/M values/multiplicities, cold eviction validity, matched BF16, sentinel-before-sweep atomicity, NCU range/metrics, setup-dominance and head readiness trigger, remote-byte equality, telemetry interval boundaries/cadence, separate useful-CUDA/exposure/cost accounting, watchdog and cleanup. Distinguish material interpretation failures from documentation gaps. Return `pass`, `pass_with_limits`, or `fail_quarantine_science` in content-addressed `AUDIT.json`.

Budgets: 15 wall minutes, 1 local CPU-hour, 256 MiB retained plus 128 MiB temporary, `$0`, no GPU/provider.
