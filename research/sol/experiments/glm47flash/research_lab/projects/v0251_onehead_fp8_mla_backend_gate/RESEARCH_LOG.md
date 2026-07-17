# Research log

## 2026-07-16 — Director opening handoff

Test the cached upstream vLLM 0.25.1 FP8 MLA producer/consumer on exact one-head L40S geometry. This is not another custom-kernel correction or generic runtime comparison. Use the proven component controller under one durable owner; actual upstream BF16/FP8 execution decides the line, and cleanup is mandatory unless the named pass trigger and ten-minute retained-session packet both qualify.

## 2026-07-16 — Single authorized allocation: operational null

Question: can the upstream v0.25.1 one-head FP8 MLA matrix reach the L40S writer/attention/reduction gate?

Action: checked shared accelerator/economic context, authenticated zero provider inventory, and launched the existing `mla_microbench_control.py` once under user systemd as `v0251-onehead-fp8-r1`. The controller was parameterized with the exact upstream benchmark and a current immutable v0.25.1 image digest after the originally listed digest failed local registry manifest resolution.

Evidence: `artifacts/upstream_onehead_l40s_20260716_r1/events.jsonl` records provider-create exit `3` at `0.613` allocation seconds; `summary.json` records `cleanup_pass=true`, `instance_get_not_found=true`, and final instance/disk counts of zero. The shared controller discarded create stdout/stderr, so the provider failure is not classifiable beyond an observability-qualified create boundary. No GPU, upstream writer, attention stage, reduction, numerical, byte, or performance result exists.

Interpretation: operational null, not a scientific close. The exact MLA hypothesis remains unmeasured, but this admission’s stop rule forbids an unchanged retry and the controller’s missing provider diagnostic prevents a stronger provider-capability claim.

Next move: only reopen with a materially corrected shared controller that retains bounded redacted create diagnostics and a separately approved admission; do not infer FP8 or L40S support from this run.

## 2026-07-16 — Director packet audit

The create failure is attributable to the unit passing the 14-line `public.pem` into cloud-init rather than the valid one-line OpenSSH public key, matching the retained invalid-YAML line-10 signature. Even after that repair, the packet would fail deterministically: wrong v0.25.1 source hashes; cross-sequence padded reshape/truncation; a byte check missing page size 16; a self-failing saturation predicate; `512^-0.5` instead of the exact `256^-0.5` scale; no separate stage timing; forced four splits while upstream selects 32 on 142-SM L40S; mismatched remote/retrieval artifact roots; and no pass-triggered retained-session handoff. Keep this packet terminal and the FP8 hypothesis unmeasured. Do not admit a paid retry until a future `$0` successor corrects all named blockers and binds the actual v0.25.1 image/source identity.
