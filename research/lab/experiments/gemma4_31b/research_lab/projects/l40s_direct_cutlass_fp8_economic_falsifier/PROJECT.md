# L40S direct CUTLASS FP8 economic falsifier

## Decision question

Does the exact installed SM89 raw CUTLASS FP8 path at Gemma 4 31B's six fused-linear shapes falsify the L40S c12 planning or conservative service ceiling after merging the independently measured attention/KV residual floor?

This is a checkpoint-free execution proxy, not an endpoint, quality, fit, reliability, or deployability test. A valid above-ceiling result closes the corresponding economic envelope. A below-ceiling result preserves only this lower bound and does not admit FP8 or a serving endpoint.

## Authoritative immutable inputs

Consume the complete packet at `../exact_shape_fp8_w4_direct_kernel_packet/` without rewriting it:

- `START_PACKET.json` SHA-256 `14bed1b4e33bd2c9dde062dec800c9a04080986d7cafcb080a5831ea156a4366`.
- `FINAL_STAGED_PROGRAM_AUDIT.json` SHA-256 `5bff874897d280a9a16318a854825ae47dbd936ef52c3341234d663065b77f15`.
- `STAGED_MANIFEST.json` SHA-256 `4b7fec791c1bd57686c3431e795e55a133adbfdd3a19381807dd769cd651f5e0`.
- `direct_fp8_kernel.py` SHA-256 `4c285c94daf032a56c0de2136badffab845503fa710dbca12027e6a345b92667`.
- `remote_stage.sh` SHA-256 `b1504265ab0131df0a1144292b0e3cbc3b6d9c9f6790c8d61ab4a1bab5a9cbc9`.
- `SOURCE_MANIFEST.json` SHA-256 `a65a36ef7abec2765c301d5508e74dd0d212bc3e3083e01a18abf577ee61149c`.

The packet mechanically binds model geometry `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, runtime image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, vLLM `0.19.1.dev6+g6d4a8e6d2`, NVIDIA L40S SM89, and the exact six Gemma fused-linear shapes at M12/M3679. `assert_identity.py` must recompute these from the packet and fail closed before any provider access if the brief or bytes disagree.

## Execution contract

Use the proven shared lifecycle `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py` through one bounded durable local systemd owner and one sequential `placement_control.VerifiedRetainedOwner` watchdog. The owner is the only process authorized to query/mutate provider state or spend. One lowercase preemptible L40S and one 100-GiB network SSD; one create; no repair, restart, checkpoint, or support successor.

Before create, require: passing director identity assertion; unchanged packet audit/manifest/program/wrapper/source/lifecycle bytes; exact L40S request; authenticated empty provider inventory; valid credentials; deadline; owner/watchdog identity; writable artifact root. Render any owner/controller wrapper within this project and bind its complete transitive byte set in a final typed pre-create terminal.

Primary stage runs only the sliding-QKV M12 sentinel. The controller must atomically retrieve and parse its terminal before starting the conditional sweep. Continue on the same retained session only when `stage==primary`, terminal/result/sentinel pass, exact runtime/source identity passes, and at least 12 provider minutes remain. Conditional stage runs exactly 12 rows: all six exact shapes at M12 and M3679, corrected signed varied-magnitude dual oracles, BF16 comparator, stable CUDA/wall distributions, accepted L40S telemetry, exact campaign aggregation, and the independent `0.1646315388888889 s/request` attention/KV residual merge. Otherwise clean immediately. W4 is not authorized.

## Budgets and terminal

- Wall clock: 38 minutes.
- Provider exposure: 26 minutes.
- Compute: 0.44 L40S GPU-hours and 2 local CPU-hours.
- Storage: one 100-GiB provider disk; 1 GiB retained plus 512 MiB temporary local artifacts.
- Spend: `$0.42` maximum; one allocation; zero repair/restart.

Stop and clean on any identity, source, hash, oracle, timing, telemetry, shape, trigger, or deadline failure. After one valid sweep, clean immediately regardless of outcome. Terminal acceptance requires retrieved typed stage artifacts, exact exposure/useful-GPU/cost accounting, watchdog identity, and authenticated zero instances/disks. Do not extend the session for compilation or W4.
