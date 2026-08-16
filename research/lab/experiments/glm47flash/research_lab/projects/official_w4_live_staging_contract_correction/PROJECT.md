# Official-W4 live staging contract correction

## Decision question

Can one bounded offline filename-contract correction prevent the already-running official selective-W4 owner from failing before its CUDA oracle, without touching the owner, provider resource, checkpoint, scientific scope, or deadline?

This is the urgent free-slot project while `glm47-official-w4-r2.service` performs runtime bootstrap. The running controller stages the project binder as `/input/official_head_shared_w4_bind.py`, but `campaign_100/nebius/remote_vllm_awq_smoke.sh` invokes `/input/head_shared_w4_bind.py`. `scp_to` preserves the basename, so the current contract deterministically fails after expensive setup unless the shared remote script is corrected before its later staging read.

## Scope

Within 300 seconds and `$0`, make exactly one shared-source correction: have the remote script invoke the staged `official_head_shared_w4_bind.py` basename. Add the narrowest fail-closed test proving that the head/shared-W4 remote invocation and `vllm_smoke_control.py` staged binder basename agree. Run only that focused test plus syntax/diff checks.

Do not inspect, signal, restart, stop, or replace the live systemd owner or watchdog. Do not call the provider, SSH to the instance, edit its artifacts/status, change scientific flags, add retention, extend the deadline, alter the official binder/oracle, or create a new controller. The live process owns all provider mutation and spend. This project only edits repository source that the existing controller has not yet staged.

Return `LIVE_STAGING_CONTRACT_CORRECTED` with source/test hashes and passing checks, or `MISSED_LIVE_STAGING_WINDOW`/a typed source conflict without making a broader repair. No successor gate.

## Evidence

- Live owner: `glm47-official-w4-r2.service`, resource `computeinstance-e00p4n86m45m1g5ftx`; create and SSH passed, runtime bootstrap began at `2026-07-16T09:44:04Z`.
- Staging: `vllm_smoke_control.py` appends `staging / head_shared_binder.name`, preserving `official_head_shared_w4_bind.py`.
- Consumer: `remote_vllm_awq_smoke.sh` currently requests the nonexistent `/input/head_shared_w4_bind.py`.
- Shared code: `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/` and adjacent tests.
