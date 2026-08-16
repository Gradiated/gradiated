# Top-3/shared raw-bound quality direct

## Question

Does the measured config-native top-3/shared candidate preserve the campaign's bounded development-quality signal when fresh serialized API responses pass through one exact identity-bound normalizer/scorer, and—only if it does—does the faster top-2/shared candidate preserve that same signal in the retained session?

## Why it matters

Top-3/shared is the best bracketed cost candidate: `644.318005` output tok/s, `1.062619x` a stable `606.349115`-tok/s top-4 control mean, and `$0.474231/M` raw planning-GPU COGS. Its prior development score fell from `0.333333` to `0.166667` on retrieval, but the archive retained raw hashes rather than serialized raw bytes and could not bind raw response to normalized scorer input. Top-2/shared is faster at `666.860853` tok/s but truncated the same retrieval case and lacks a completed bracket. The campaign now has several credible performance candidates, so one execution-bearing candidate-specific quality localization is more valuable than another performance sweep or quality-seal project.

This is a direct model experiment, not a repeat performance benchmark or broad quality certification. The previous top-3 no-retry rule is overridden once only for a new raw-bound quality measurement; its completed performance bracket remains immutable and is not re-promoted from this run.

## Exact inputs and path

- Checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Top-3 config `../full47_top3_shared_c32_direct/artifacts/l40s_top3_shared_c32_20260716_r1/configs/top3_shared_config.json`, SHA-256 `836bba9776aa1de99d7d8121a8f3abce374b1630f1821fb4d39813b1d06b3861`.
- Conditional top-2 config `../full47_top2_shared_c32_direct_corrected/artifacts/l40s_top2_shared_c32_20260716_r2/configs/top2_shared_config.json`, SHA-256 `b592960b89f80337618f980dbfb0ec048698f3b8fa30c5cb14479b24170ef255`.
- Proven launcher/recovery path: `campaign_100/nebius/vllm_smoke_control.py` and `vllm_recover_existing.py`, pinned vLLM 0.15.0 L40S AWQ runtime.
- Existing candidate-specific six-case development suite, exact BF16 control responses, tokenizer, normalizer, `score_pair.py`, and prospective NLL ceiling already used by the measured top-3/top-2 arms. Do not substitute the BF16-V2 calibration suite or create a new policy.

Finish the existing AWQ consumer bridge only as required for the live decision. It must persist each serialized raw API response, canonical normalized candidate rows, one-to-one raw/normalized bindings, exact scorer stdout/stderr/result, and an identity manifest binding suite/fixture, checkpoint plus selected config, runtime image/Transformers/server command, normalizer source, scorer source, and BF16 control bytes. Before create, pass one representative recorded response through the actual consumer and prove raw, normalized, suite, model/config, runtime, and scorer mutations all fail closed. Then launch in the same researcher turn. No standalone manifest, seal, controller, or further repair project; inability to reach the actual consumer closes locally.

## One sequential allocation

Authorize one preemptible Nebius L40S create, no retry, at most `2,800` allocation seconds and `$0.70` actual exposure. Use the shared `VerifiedRetainedOwner` around the whole sequence plus one independent absolute instance/disk watchdog. Before create, exercise real typed success, false trigger, insufficient reserve, consumer failure, and cleanup-failure branches. Terminal success requires a typed final quality classification and fresh authenticated zero instance/disk inventory.

Run top-3/shared at c32 only: cache off, BF16 KV, four KV splits, max-seqs 32, 65,536 batched tokens, 64 exact 8,192-input/1,024-output requests, and a 300-second background envelope. Record full request/token rows, raw quality bytes and bindings, exact scoring lineage, semantics, cache-zero evidence, throughput and latency, HBM/telemetry, useful GPU seconds, actual exposure, artifact hashes, and cleanup. Treat fresh c32 throughput as identity/drift evidence only; the prior top4/top3/top4 bracket remains the performance authority.

Measured setup/bootstrap/checkpoint staging (~`1,151 s`) dominates one scored arm (~`361 s`), so preregister exactly one adjacent cross-project follow-up: `VALID_TOP3_RAW_QUALITY_ENABLES_TOP2_RAW_QUALITY`. Prepare the content-bound top-2 config and consumer inputs offline before the owner starts. The trigger is true only if top-3 has a typed full-load c32 endpoint, exact raw-bound consumer pass, no negative overall point regression versus its BF16 control, no critical/catastrophic category regression, prospective NLL pass, semantic/cache evidence, and at least `800 s` remaining for one retained arm plus cleanup. On true, reuse only the verified content-bound runtime and unchanged checkpoint, apply and verify the content-bound top-2 config override, run the same c32/raw-quality arm, then clean. On false or insufficient reserve, clean immediately. No checkpoint restage, manual attach, or third arm.

## Decisions

- `TOP3_RAW_QUALITY_SIGNAL_FAIL`: top-3 fails the exact bounded signal; close top-3 and do not run top-2.
- `TOP3_RAW_QUALITY_SIGNAL_PLAUSIBLE`: top-3 passes but top-2 is not admitted by trigger/reserve; preserve top-3 for a later separately authorized quality-eligibility decision.
- `TOP2_RAW_QUALITY_SIGNAL_PLAUSIBLE`: both pass; preserve top-2 as the higher-throughput quality-plausible candidate, still limited by its old missing performance bracket.
- `TOP2_RAW_QUALITY_SIGNAL_FAIL_PRESERVE_TOP3`: top-3 passes and top-2 fails; preserve top-3.
- `TYPED_OPERATIONAL_CLOSE`: no valid primary consumer/endpoint; no retry or successor.

Every result is candidate-specific development evidence only—not holdout certification, deployability, sustainable all-in admission, or a provider-beating claim. Do not run stock/top-4, combined/selective W4, c16/c36, split-8, training, recovery, broad evaluation, methodology benchmarking, or another provider session.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/lab/experiments/glm47flash/campaign_100`
