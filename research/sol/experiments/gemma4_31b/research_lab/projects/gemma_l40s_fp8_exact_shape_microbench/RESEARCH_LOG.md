# Research log

## 2026-07-17 — director delegation

Activated as the sole paid lane after closing the full-endpoint staging lineage. The scientific target is deliberately narrower: exact-shape Ada BF16/FP8 kernel support, numerical behavior, timing, and memory mechanisms without checkpoint or server setup. Use the shared proven controller, honor the typed pre-create gate and budgets, and leave `artifacts/summary.json` plus verified cleanup. The conditional same-image FP8-KV arm runs only if the primary FP8 linear gate passes.

## 2026-07-17 — typed pre-create image-identity blocker

Question: can the admitted exact-shape CUDA microbenchmark safely create its single L40S allocation with the frozen runtime identity?

Action and evidence: wrote `artifacts/preflight-20260717T000000Z.json`; grouped checks found zero provider instances and disks, all local inputs present, and verified both candidate registry identities. The digest required verbatim by `PROJECT.md`, `sha256:952594c7e9337f1d3495ef2f0b3ebf3049791484a9d937c9d0da9f8488ea2520`, fails registry manifest verification. The authoritative FP8 and FP8-KV packets instead agree on `sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, which resolves to the recorded amd64 manifest `sha256:8e86cb93b724092cd4dc892fb129a6c5538613b38a5cd34e40aab9e6aea72b03`.

Interpretation: this is an in-scope external pre-create blocker, not FP8 or L40S evidence. Choosing the resolvable packet digest would silently change the PROJECT-frozen image identity, so no provider resource or durable owner was started.

Next move: director reconciliation of the immutable image identity, then rerun the recorded preflight and launch the shared controller under the declared durable service command.

## 2026-07-17 — director identity reconciliation

The authoritative geometry, FP8, and FP8-KV packets mechanically agree on model, revision, workload, vLLM revision, runtime manifest-list digest, and amd64 child manifest. Corrected the brief to those extracted identities and added `validate_identity_contract.py` as the provider-create assertion. The original failed preflight remains preserved as negative delegation evidence. The same project now continues through the narrow shared-controller image-argument change, rerun preflight, durable owner, typed terminal, and cleanup; no successor project or provider resource was created by the director.

## 2026-07-17 — durable exact-shape owner started

Action: `validate_identity_contract.py` passed. Added the shared controller's explicit `--runtime-image` argument and a narrow behavior test proving it reaches both bootstrap and container command; the focused controller test suite passed. The rerun typed preflight is `artifacts/preflight-20260717T001000Z.json`, with empty provider inventory, the reconciled image identity, exact-shape BF16/FP8 script, and conditional same-image KV arm.

Execution: started `gemma-l40s-fp8-exact-shape-owner.service` under user systemd (PID 1853023, invocation `8314464e7ba24a2c9b47bb6d57d1f257`, deadline 2026-07-17T05:33:39Z). The grouped snapshot captured the controller cgroup, its provider-create subprocess, `provider-request.json`, artifact root `artifacts/gemma-l40s-fp8-exact-shape-20260717t001000z`, and the named resource. The controller will bind the resource and start its cleanup watchdog once creation returns. Do not poll or restart this owner; reconcile its typed terminal and inventory on the next project turn.

## 2026-07-17 — first CUDA terminal reconciled; one correction admitted

The owner entered the conditional KV arm, proving every primary FP8 linear case passed the registered finite-output and absolute-error gate, then OOMed on a monolithic 28.29 GiB all-layer BF16 KV tensor before writing buffered detail. Its repair window expired normally; `summary.json` records 1,211.451 provider seconds, `$0.255388046` derived cost, authenticated artifact retrieval, cleanup pass, and zero final instances/disks. The director admitted one final in-place allocation under a 20-provider-minute/$0.50 correction cap, consuming the source-reconciled per-layer/tiled KV arm and atomic primary persistence. A third allocation is prohibited.

## 2026-07-17 — final corrected owner started

Action: consumed `KV_CONTRACT.json` and `CORRECTED_ARM.md`; identity validation, empty authenticated provider inventory, focused shared-controller tests, and the injected KV-failure atomic primary-persistence check passed. The correction pre-create terminal is `artifacts/correction-preflight-20260717T000000Z.json`. The benchmark now emits its primary rows by fsync-and-rename before conditional KV work, and processes source-bound local/global cache layers separately in 128-token conversion/readback tiles.

Execution: started the single final `gemma-l40s-fp8-exact-shape-correction-owner.service` under user systemd (PID 1862700, invocation `27194f2daec84bab92cec7614d149639`, deadline 2026-07-17T05:08:53Z). The grouped snapshot captured the controller cgroup, named resource create subprocess, and `provider-request.json` at `artifacts/gemma-l40s-fp8-corr-20260717t000000z`. Do not poll, restart, or create another allocation; reconcile the typed terminal, retrieved primary/KV artifacts, and cleanup on the next project turn.

## 2026-07-17 — corrected terminal closed as a partial mechanism pass

The final owner returned `PASS` after 621.989 provider seconds and `$0.131122547` derived spend; the authenticated archive contains 14 files, SHA-256 `922ebaeb41d3b8d1353e68c6fc37e707192cdb3be29216fa26f751ed81336146`, and cleanup verified zero instances and disks. Generic `torch._scaled_mm` BF16/FP8 rows were finite and below the registered absolute-error threshold, and the tiled PyTorch E4M3 conversion/readback rows passed. `useful_gpu_seconds` is absent, so no useful-time efficiency claim is made.

Director source reconciliation rejects the advertised exact-shape scope. At TP=1, pinned vLLM computes sliding QKV output as `32*256 + 2*(16*256) = 16384`, global QKV as `32*512 + 2*(4*512) = 20480`, global attention output input as `32*512 = 16384`, and merged gate/up as `2*21504 = 43008`. The harness used `12288`, `6144`, one `8192→5376` output case, and `21504`. Its KV arm called `torch.Tensor.copy_`, not the pinned vLLM cache writer. Preserve the exact down-projection, sliding output, generic Ada FP8, and synthetic KV rows as partial evidence only; do not create a third allocation or use this terminal as endpoint, quality, throughput, or exact-consumer evidence.
