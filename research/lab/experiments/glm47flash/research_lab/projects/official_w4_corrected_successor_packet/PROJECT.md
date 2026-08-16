# Official-W4 corrected successor packet

## Decision question

Can the deterministic staged-binder basename mismatch be corrected and source-bound at `$0` so a fresh official selective-W4 allocation reaches the CUDA oracle immediately after the current pre-science owner cleans up?

The current owner has already staged `remote_vllm_awq_smoke.sh` invoking `/input/head_shared_w4_bind.py`, while its controller copied `official_head_shared_w4_bind.py`. It will fail before the CUDA oracle; this is operational evidence only. The scientific W4 intervention remains campaign priority one.

## Bounded correction

Within 600 seconds and no provider mutation:

- change only the remote invocation to `/input/official_head_shared_w4_bind.py`;
- add a focused fail-closed test that the remote invocation matches `head_shared_binder.name` staged by `vllm_smoke_control.py`;
- run the focused test, Python/shell syntax checks, and diff check;
- emit before/after hashes and one immutable corrected launch command for `full47_official_selective_w4_cuda_endpoint_corrected`.

Do not edit the official producer, root, binder logic, CUDA oracle, model/runtime/workload, live owner/artifacts, provider state, or deadline. Do not add a custom controller or another readiness project. The current launcher lacks a named result evaluator and cannot safely make the stock comparator ready within ten minutes; record that boundary and require normal cleanup for the corrected successor rather than adding unconditional retention.

Return `CORRECTED_W4_PACKET_READY` or a typed `PACKET_CLOSE`. A ready result is consumed directly by the already-delegated GPU successor; no additional gate.

## Inputs

- `../full47_official_selective_w4_cuda_endpoint/`
- `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`
- `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/remote_vllm_awq_smoke.sh`
- `/root/workspace/research/lab/experiments/glm47flash/campaign_100/tests/test_nebius_vllm_smoke_control.py`
