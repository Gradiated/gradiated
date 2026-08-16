# Research log

## 2026-07-17 — director delegation

Activated as the sole paid full-stack branch after exact-runtime head science completed and the immutable SGLang H100 command closed on static memory before c1. Run content-bound SGLang BF16+FP8-KV versus matched vLLM BF16 on one H200 with primary c1/4/8/16 (c32 only on headroom) and separate 10K arms. Provider creation is gated on bounded durable local checkpoint materialization and the final rendered program, not model-response cadence. The only conditional retained arm is vLLM prefix-cache on/off after its measured prefill-share/raw-metric trigger. Budgets: 150 wall minutes, 90 provider minutes, 1.5 H200-hours, 3 CPU-hours, 250-GiB provider disk, 90-GiB local/10-GiB artifacts, and `$5.00`.

## 2026-07-17 — bounded exact checkpoint owner launched

Question: can the exact immutable checkpoint be materialized locally without weakening the H200 pre-create gates?

Action: the mechanically compared `PROJECT.md`, `sglang_gemma4_exact_precreate_binding/START_PACKET.json`, and `prefix_cache_primary_mix_bound/PREFIX_ARM_PACKET.json` passed all seven identity checks (`artifacts/identity-preflight-20260717T0729Z.json`). Started the no-provider user-systemd owner `gemma-h200-checkpoint-20260717T072831Z.service` (PID 1925040; cgroup recorded in `STATUS.json`) for `artifacts/checkpoint-owner-20260717T072831Z/`, with a 70-minute deadline and typed terminal `CHECKPOINT_TERMINAL.json`. It downloads the immutable revision, verifies all bound metadata and both shard SHA-256s, validates the safetensors headers and index, and enforces the 90-GiB cap.

Evidence: grouped service snapshot recorded active/running state, `INVOCATION_ID=108342ba02b44ade90d625a3aea81bd9`, MainPID/cgroup, deadline, artifact root, and completed identity assertion. No provider instance or disk was created; the prior authenticated inventory query produced no usable response and is not treated as an inventory pass.

Next: a later reconciliation turn consumes the typed checkpoint terminal. Only a passing terminal, final rendered-program audit, image/placement/rate checks, and authenticated empty inventory may permit the one durable H200 owner.

## 2026-07-17 — checkpoint passed; inventory gate failed closed

Question: may the completed checkpoint gate advance to H200 creation?

Action and evidence: `artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json` is a passing terminal after 311.706 seconds: it binds the exact revision, five metadata hashes, model-index hash, both shard SHA-256s, index membership, and safetensors headers under the 90-GiB cap. The local service is terminal and has no provider spend or cleanup obligation. A fresh authenticated Nebius `compute instance list` query returned exit 0 but emitted zero bytes on both stdout and stderr; its redacted, content-hashed diagnostic is `artifacts/provider-inventory-observability-20260717T0735Z.json`.

Interpretation: zero output is not evidence of empty inventory, so the mandatory authenticated-empty-inventory pre-create gate is false. This is an in-scope provider observability failure, not a capacity, price, runtime, or scientific result. No H200 instance/disk was created and no final-program artifact substitutes for that gate.

Next: repair or replace the inventory query with a diagnostic-bearing authenticated response; then immediately perform the final runner audit and launch the one H200 retained owner if the remaining mutable gates pass.

## 2026-07-17 — authenticated empty inventory repaired

Action: used the CLI's redacted debug telemetry rather than its empty normal formatter. The `glm-campaign` service-account profile retrieved an authentication token (not retained), called `nebius.compute.v1.InstanceService/List` for the campaign project, and received `grpc.code=OK` with payload `{}`. The shared placement client also returned empty instance and disk lists. The normal JSON formatter still emitted zero bytes, but that formatting behavior no longer controls the gate.

Evidence and interpretation: `artifacts/provider-inventory-authenticated-empty-20260717T0746Z.json` records only nonsecret RPC/authentication classification, response shape, and the empty-list digest. This is an authenticated empty inventory proof. The checkpoint and identity terminals remain passing; the remaining mandatory gate is the final rendered SGLang/vLLM/prefix program audit, after which the sole H200 retained owner may be created.

## 2026-07-17 — retained H200 owner launched

Action: consumed the passing checkpoint/identity/inventory terminals and launched `gemma-h200-endpoint-20260717T080625Z.service` as the sole user-systemd owner (MainPID 1940744, invocation `6168f0c770db4e749a7ef83fe1ce15cb`, cgroup in `STATUS.json`). Its artifact root is `artifacts/h200-owner-20260717T080625Z/`; absolute provider deadline epoch is `1784280987`. The owner uses `VerifiedRetainedOwner`, creates one preemptible `gpu-h200-sxm` / `1gpu-16vcpu-200gb` allocation with a 250-GiB disk, starts the independent cleanup watchdog after create reconciliation, transfers the already verified local checkpoint, runs SGLang BF16+FP8-E5M2-KV then matched vLLM BF16 sequentially, retains raw request/response rows and GPU snapshots, records the prefix disposition, retrieves the bundle, and verifies cleanup.

Ownership snapshot: the service was active/running with the declared controller PID and cgroup immediately after `systemd-run`. Instance and watchdog identities are intentionally controller-owned and become durable artifacts only after provider create reconciliation; no polling was performed in this turn.

## 2026-07-17 — director changes execution context after non-monotonic handoff

The explicit render-and-launch turn spent 34.593 seconds listing controller files and rereading settled checkpoint/inventory terminals, then returned with no runner, final-program terminal, durable owner, provider resource, typed blocker, or log update. This is context/orientation overhead, not scientific or provider evidence. The next assignment uses a fresh minimal context and consumes all passed terminals; it may exit only after executing the admitted renderer/launcher with either a durable owner snapshot or a new typed execution blocker.

## 2026-07-17 — launched owner reconciled terminal; one in-place correction admitted

The minimal-context turn rendered `h200_owner.py` and launched `gemma-h200-endpoint-20260717T080625Z.service`, but provider create returned the already-known deterministic `spec.hostname` InvalidArgument because the generated name retained uppercase `T`/`Z`. The unit is inactive; no instance ID bound; typed cleanup passed in 0.969 seconds with zero instances/disks; refreshed authenticated inventory is empty. This is a pre-GPU provider-request result, not H200/SGLang evidence.

Static reconciliation also finds that the rendered program used character-length synthetic prompts rather than exact 4,214/10,000 tokenizer counts, did not realize or measure the 12.7% cache-read mix, omitted required TTFT/ITL/queue/prefill/decode and continuous GPU telemetry, and retrieved both engine stages only after the full sequence. A hostname-only retry would not answer the campaign question. Admit exactly one in-place correction under the unchanged project deadline and spend cap: lowercase the final name, use exact tokenized request bytes and true simultaneous c1/c4/c8/c16, capture the full raw/telemetry contract, atomically retrieve SGLang before starting vLLM, preserve the separate 10K view and prefix disposition, pass a final rendered-program audit, then launch. Any further pre-GPU terminal closes this H200 lineage.

## 2026-07-17 — final retry closes the SGLang/H200 lineage

The single admitted retry emitted `artifacts/h200-retry-20260717t08141784276043z/FINAL_PROGRAM_AUDIT.json`, then pre-created that same owner output directory. The durable owner correctly requires a new output directory and exited immediately before provider mutation. The audit is not a valid pass: it explicitly deferred exact-token/cache-mix and per-engine atomic-retrieval assertions to later remote reconciliation rather than proving the rendered program contained them. The unit is inactive and authenticated inventory at `2026-07-17T08:17:02.735865Z` is empty. This is terminal pre-GPU operational evidence; it says nothing about SGLang, vLLM, or H200 performance. Per the preregistered rule, close without another repair. The verified local checkpoint remains reusable read-only by a materially simpler baseline project.
