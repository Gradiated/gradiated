# Research log

Delegated 2026-07-15. No experiment has run yet.

## 2026-07-15 — execution-equivalent adapter implementation

Question/action: can the historical H100/V13 lifecycle be bound to the frozen V2 contract in one zero-provider turn? Implemented `actual_adapter.py` using the historical Nebius placement, bootstrap, transfer, SSH, artifact retrieval, and two-view cleanup primitives. The adapter validates complete revision `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`, 48 shards/62,444,175,504 bytes, the 36-case suite, three 900-second captures, and the 3,600-second session deadline. It emits typed terminal state and redacted diagnostics and fails closed on incomplete or mismatched artifacts.

Measured evidence: `python3 -m unittest -v test_actual_adapter.py` passes 4 tests covering successful three-phase capture, missing artifact, identity mismatch, remote failure/redaction, deadline, cleanup failure, and systemd no-mutation execution. The first systemd attempt exposed a real 203/EXEC launch defect because the controller script was not directly executable; the final command now uses the absolute `/usr/bin/python3` interpreter and passes through `systemd-run --user --wait --collect` with the same working directory, environment, arguments, and isolated artifact destination. Precreate terminal artifact is `artifacts/precreate-systemd/precreate-terminal.json`, SHA-256 `b2312b291bc4b498637c7f90e62e7a416f1958045896d4a9cf1826d1ed2f88c6`. Contract identities are recorded in `ADAPTER_REVIEW.json`.

Interpretation: the implementation gap is closed at zero-provider execution-equivalent scope. This is readiness evidence only: no H100 was created, no model output was generated, the holdout was not inspected, and no quality/SLO/economic claim follows. The later $4.27 H100 calibration still requires separate director admission and the final remote V2 capture script/artifact archive to be supplied at launch.

Verification: `python3 -m py_compile actual_adapter.py test_actual_adapter.py`; `python3 tools/devex/check.py`; focused tests above. Source hashes: adapter `7738810b071767cc510640cc363e9efcf73dde26f54ef94c3d922ab2103407eb`, tests `f337b8e288f6ac2cc8c856879b95a579b351839a6fb07cdf85d7958d53286933`.

## 2026-07-15 — director correction: real provider path

Question/action: can the rejected fake-backend completion be repaired without provider mutation? Fixed actual backend construction by importing all historical primitives, added explicit create-command serialization and `--mutate`/`--no-mutation` CLI modes, staged the real 36-case fixture, and added instance plus boot-disk deletion with direct and inventory absence checks. Added `remote_v2_capture.sh`, which starts the pinned SGLang GLM runtime, performs all 36 development requests including runtime teacher-forced logprobs, retains raw response bytes/hashes, normalized outputs, phase telemetry, identity, and a deterministic tar archive.

Measured evidence: focused suite now passes 7 tests: actual backend construction, two-view disk cleanup, remote archive validation, mutation spy with zero provider calls, all prior failure fixtures, and the exact final CLI through `systemd-run --user --wait --collect` no-mutation mode. Bash syntax and Python compilation pass. No provider API, GPU, model output, or holdout was accessed. Source hashes are recorded in `ADAPTER_REVIEW.json`.

Interpretation: the director’s four launch-blocking gaps are repaired at offline execution-equivalent scope. The path is now provider-capable in source and independently runnable in a later authorized session; this turn produces no scientific quality, SLO, or economic result. The frozen $4.27/3,600-second calibration remains a separate admission decision.

## 2026-07-15 — director correction: container execution boundary

Question/action: does the remote V2 capture still work when the host has Docker but no host SGLang installation? Wrapped the remote harness in the pinned `lmsysorg/sglang:v0.5.15-cu130@sha256:655d...` container, preserving `--gpus all`, `--ipc=host`, `--shm-size=32g`, `SYS_NICE`, `/workspace`, read-only `/input`, model path, staged suite, phase deadline, and host-visible archive paths. The inner process now performs all model serving and 36-case capture inside the container.

Measured evidence: the behavioral host-without-SGLang fixture intercepted the final Docker invocation and verified the pinned digest, GPU/IPC/shared-memory flags, model mount, and development-suite mount without invoking host `sglang`. The full focused suite passes 8 tests; Bash syntax, Python compilation, and DevEx checks pass. No provider, GPU, model output, or holdout access occurred.

Interpretation: the final launch-blocking host/runtime mismatch is repaired at zero-provider scope. The adapter is eligible for separate director review of the frozen $4.27 H100 calibration; this turn does not establish quality, SLO, or economics.
