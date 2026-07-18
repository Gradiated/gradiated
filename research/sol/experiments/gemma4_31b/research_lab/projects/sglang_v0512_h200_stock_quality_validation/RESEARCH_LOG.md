# Research log

## 2026-07-18T10:27:03Z — director admission

The exact stock SGLang v0.5.12 H200 candidate completes 32/32 workload requests at `2.752522 req/s` and `0.363303 s/request`, passing the strict market ceiling by 23.0%. Native NEXTN MTP is unmeasured because the immutable image's Transformers rejects `gemma4_assistant`; do not repair or infer that arm here. Activate one retained H200 quality/feature project pairing the working FP8-E5M2-KV candidate with same-runtime BF16 KV and a small direct Transformers reference sentinel. Use fresh Gemma-specific raw captures and executable scorers; reuse only generic capture mechanics. Limits are 120 wall/70 provider minutes, 1.1667 H200-hours, one 250-GiB disk, and `$3.25`.

## 2026-07-18T10:32:35Z — paired quality owner launched

Question: whether the stock H200 FP8-E5M2 KV market pass remains text-quality eligible against same-image BF16 KV. Action: built and locally validated the project-owned raw-capture suite (`suite_sha256` `95a15bc6ab5180bde9d9141b68a7191a11b1ec9f6994d44d8196c3b614d1209f`), then launched durable user-systemd owner `gemma-h200-paired-quality-20260718t10321784363555z.service` (PID `2367420`, deadline epoch `1784374955.8630693`). Evidence: its typed `PRECREATE_TERMINAL.json` passed all binding, checkpoint, suite, key, empty-inventory, and time checks. The owner is in development mode and owns sequential BF16 capture, FP8 capture, raw-only scoring, direct Transformers sentinel, retrieval, and authenticated cleanup; provider resource identity and watchdog will be emitted atomically after create.

## 2026-07-18T10:37:07Z — retained transfer repair

The shared `scp_to` helper's fixed 180-second timeout interrupted the 62.58-GB transfer after 11.89 GB of the first shard; remote disk remained healthy with 214 GB free and no model/runtime failure occurred. The original owner entered its explicit repair lease. A bounded user-systemd transfer helper (`gemma-h200-paired-quality-20260718t10321784363555z-transfer-repair.service`, PID `2370807`) is completing the exact same bound checkpoint onto the retained instance; it creates no provider resource and leaves the original owner/watchdog responsible for later retry, science, and authenticated cleanup.

## 2026-07-18T11:21:16Z — checkpoint repair consumed

The in-place helper completed, and the retained owner consumed its actual retry path: checkpoint-transfer attempt three passed, followed by the owner’s remote checkpoint/suite validation on attempt one. The owner is now pulling the immutable image on the same claimed H200; no model, runtime, or quality result exists yet.

## 2026-07-18T11:34:37Z — BF16 control capture repaired and passed

The first capture's HTTP 400 was a suite request-geometry failure, not a server or precision result: `context_token_####` expands beyond the 5,000-token server context. A direct resident BF16 request returned HTTP 200 and `323`. Replaced the long filler with 4,100 tokenizer-friendly `the` tokens, retained HTTP error bodies in the runner for future failures, and transferred the new content-hashed suite to the resident workspace. `control_capture` attempt two completed successfully and its terminal was retrieved before the owner sequentially started the FP8-E5M2 arm.

## 2026-07-18T11:41:29Z — typed paired-quality close

The direct Transformers sentinel completed with prompt-token identity and 240 scored tokens. The atomic paired terminal is false because the executable Python control case failed under BF16 (`control_pass: false`); this invalidates the control, so the quality claim is quarantined as a runtime/control failure rather than an FP8 candidate regression. An earlier observed FP8 deterministic-repeat mismatch remains an unpreserved provisional observation and cannot be erased by the later retry, but it also cannot support a raw-evidence candidate verdict. Authenticated cleanup passed with zero matching instances and disks.
