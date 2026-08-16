# Minimal-depth-42 direct L40S measurement

## Question

Does the smallest materialized physical-depth candidate with robust c32 headroom actually load on L40S and clear the campaign's `594.466` output-token/s (`$0.514/M` at `$1.10/hour`) gate on the exact 8,192-input/1,024-output background workload?

## Why it matters

The 42-layer proxy is the nearest executable divergence found after the full 47-layer c32 path remained operationally unmeasured. Removing source blocks `[6,15,24,33,42]` projects c32 at `43,666.023 MiB`, leaving `2,401.977 MiB` against the observed 46,068-MiB envelope. Its `597.529` tok/s analytical bound is only 0.515% above the gate, so another bound cannot decide it. The physical rewrite preserves all retained tensor shapes and the existing compressed-tensors W4 kernels; only five complete serving blocks and their KV state disappear.

## Fixed inputs and evidence

- Candidate root: `/root/.cache/glm47flash-awq-minimal-depth-4c84badbce22`; source revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`; contract `4c84badbce2290a95ebc83bbceb784fce28507e15038fc6a60105ed5350697cf`.
- Four shards / `16,658,558,680` weight bytes; manifest SHA-256 `a41e353015487ff58d367bf5ce42ae7c7d49de87c339c49deab714a69a42a584`; checksum-list SHA-256 `eb65906a02e4ed6a69a04e403592157ece5a9e672aabe27bdcc1633b42c441dd`; config `3859511a5a451f8d9a5fd0dd10e25edd98dd40cc4e970d4a124047dc86982899`; index `8758d9236670cb1c0f693ce6b54f7a9318c85c76feb8b333b8e0429a0113edde`.
- Tokenizer root: `/root/.cache/glm47flash-awq-ab31d120`; tokenizer/config/template hashes remain `353a3ff9...`, `b6b807f7...`, and `d63ad536...` as recorded in the parent project.
- Proven launcher: `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, current SHA-256 `9428e793515d1a22570b290222f24312970d6f3128c4b814ac24a3f6ccb55599`; remote script `fee4b95fb807c84fc76ed94ae12d175937461ab73389ded18f3611eba8cfecfc`; runner `96bfd33e7d1fcdc17646ea9d357e659b3a01fcf69c200cb7dd70e1ff922f39f6`.
- Runtime: vLLM 0.15.0 image digest `97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543` plus Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`.

## Scope and immediate experiment

The shared local and remote AWQ validators currently identify every derived checkpoint as the exact student39 payload. Make one narrow content-addressed correction: extend their exact allowlist/map for the student42 hashes and bytes above while preserving stock and student39 behavior. Tests must cross-reject stock, student39, student42, and any drift; never trust arbitrary manifest-declared bytes or rewrite the candidate. Record post-correction source hashes. Continue in the same researcher return through execution-equivalent no-mutation validation and provider measurement; a launcher patch or readiness artifact alone is not terminal.

Use the corrected shared launcher as the direct external-systemd `ExecStart`, with `--profile l40s-awq`, `--scientific-mode awq`, `--num-kv-splits 4`, `--max-num-seqs 32`, `--frontier-concurrencies 16,24,32`, `--background-arm-envelope-seconds 300`, and `--absolute-timeout-seconds 3900`. Run one server and two complete batches at each candidate concurrency with prefix caching off. Do not run stock, training, recovery, broad quality, FP8 KV, MTP, another checkpoint, or a project-specific controller. One material in-place correction after create is allowed.

Record real loader/key consumption, compressed-tensors dispatch, peak/steady memory, exact request rows, throughput, completion/TTFT/TPOT, prefix-cache deltas, GPU utilization/power/clocks, semantic diagnostics, useful GPU seconds, provider exposure/spend, content hashes, and verified zero final inventory. The existing deferred-quality diagnostic may reject the untrained proxy; preserve and adjudicate complete performance arms independently as for student39.

## Budget and decision

This is the sole provider-mutation project. Maximum exposure is 3,900 seconds and `$1.00` at the measured `$0.8581222/hour` VM-plus-disk rate, including cleanup. Any complete arm is an economic-proxy pass only if all requests finish within 300 seconds and it reaches at least `594.466` output tok/s. Report c32 as the primary decision and c16/c24 as the placement curve. A valid load/OOM/sub-gate result closes this five-block candidate; a pre-GPU operational failure is null but receives no controller-successor project. Quality remains mandatory before deployment and is explicitly deferred here.

## Artifact contract

Produce one experiment spec, retained raw arm bundle, exact identity and loader evidence, terminal economic result, spend/useful-GPU accounting, cleanup receipt, and a concise `RESEARCH_LOG.md` update.
