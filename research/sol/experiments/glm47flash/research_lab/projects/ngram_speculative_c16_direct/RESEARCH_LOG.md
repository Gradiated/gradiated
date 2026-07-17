# Research log

Opened by the Cycle 84 director as the sole paid lane. This is a direct candidate endpoint, not a speculative-decoding survey: bind one pinned prompt-lookup method, make one narrow shared-launcher switch, and launch in the same return or close at `$0`.

## 2026-07-16 — launched sole c16 n-gram candidate

Question: can target-verified prompt lookup clear `594.466` output tok/s on exact current-AWQ L40S c16? Action: the pinned vLLM `v0.15.0` source gate passed (`SpeculativeConfig` source SHA-256 `75f4956a1399790f7e7fdf80d14eeb5524da486a1b94077fdf5fb37f8ee138b5`); it accepts `method="ngram"` and binds the target configuration. Added the fail-closed `--ngram-prompt-lookup` launcher switch, pinning `{method: ngram, num_speculative_tokens: 5, prompt_lookup_min: 5, prompt_lookup_max: 5}` exclusively to AWQ L40S c16. The focused shared-launcher suite passed (`36` tests); stock mode remains without `--speculative-config`, methodology remains off, and the existing runner retains per-request output-token histograms/completeness and stream hashes.

Evidence/ownership: grouped preflight found the exact local manifest and tokenizer files and zero starting Nebius instances/disks. External systemd controller `glm47-ngram-spec-c16-r1.service` PID `1316939` created `computeinstance-e00aebh93j0tcxchbd` (`RUNNING`) and began SSH readiness. Its independent absolute-cleanup watchdog is `glm47-ngram-spec-c16-r1-watchdog.service` PID `1317149`; deadline is `2026-07-16T04:47:09.890374Z`; artifact root is `artifacts/ngram_speculative_c16_direct_2026-07-16-r1`. Do not poll here: reconcile the terminal archive, histogram completeness, acceptance evidence, economics, and authenticated cleanup on the next scheduled turn.

## 2026-07-16 — retained-owner snapshot

One grouped snapshot confirms the same controller PID/cgroup and watchdog PID/cgroup remain active, the named L40S instance remains `RUNNING`, SSH readiness completed at `03:53:39Z`, and runtime bootstrap began at `03:53:42Z`. No provider mutation or endpoint polling was performed; terminal reconciliation remains the next action.

## 2026-07-16 — retained-owner snapshot: transfer

The same live controller and watchdog own the running named instance and boot disk. Runtime bootstrap completed after `404.524` seconds; the pinned CUDA/Transformers preflight passed, the tiny-transfer probe SHA-256 is `6967780b45a5e9e86c4e5ac54e2595fcf2add1a66cdd63cb8df63017fa8c8d11`, and checkpoint transfer started at `04:00:34Z`. No completion or endpoint inference is made; defer terminal reconciliation.

## 2026-07-16 — retained-owner snapshot: scientific workload

The controller and watchdog remain active with the same named L40S instance and disk. Immutable transfer completed in `324.989` seconds (`14/14` files; `20,193,158,555` bytes), then the single `scientific_workload` phase started at `04:05:59Z`. No endpoint, artifact, or cleanup inference is made in this turn.

## 2026-07-16 — terminal reconciliation: SCIENTIFIC_FAIL

The sole candidate completed and both named provider inventories are empty. The authenticated archive SHA-256 is `b1a2381cb414a424bddcc3ce2a2b4fc234e397a154616fd15691ea8f13c593c7`, with a verified 37-file internal manifest. N-gram was actually active: the server recorded the pinned five-token configuration and `27,844` accepted tokens (`5,616/5,575/5,574/5,540/5,539` by draft position). All 32 exact c16 requests succeeded with complete output-token histograms (32,768 total output tokens); semantic determinism and paired relative-quality evidence passed.

Despite that high acceptance, vLLM disabled asynchronous scheduling for n-gram decoding and the endpoint delivered only `90.8004806` output tok/s over `360.879147` seconds, missing both the `594.466` tok/s and 300-second gates. At the actual `$0.8581222/hour` rate it is `$2.625176/M` output tokens, versus the `$0.514/M` target. Exposure was `$0.363682523` (under the `$0.80` cap), useful GPU time `360.879` seconds, and cleanup passed with zero final instances/disks. This is a valid negative endpoint result; no sweep or successor is authorized. See `TERMINAL_RECONCILIATION.json`.
