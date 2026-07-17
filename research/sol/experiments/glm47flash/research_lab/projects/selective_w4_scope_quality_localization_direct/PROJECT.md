# Selective-W4 scope quality localization direct

## Question

Can either isolated official group-32 W4 scope—`lm_head` only or the 46 serving shared experts only—preserve the combined candidate's full-47 c32 economics while removing its development-quality regression?

## Why it matters

Combined official head+shared W4 is the strongest measured exact-full-47 representation candidate: c32 completed 64/64 exact 8K/1K requests at `630.195398` output tok/s, `$0.484858/M` output at the campaign's `$1.10/hour` planning rate, and `2,323 MiB` observed HBM headroom. It is not quality eligible: its normalized development result fell from the carried BF16 control's `0.333333` to `0.0`, with retrieval and continuation regressions. The current archive cannot bind that interpretation to serialized raw API bytes, so replaying it would only repeat the prior artifact close.

The portfolio now contains several credible performance candidates, satisfying `CAMPAIGN.md`'s condition for bounded candidate-specific quality triage. This is not broad certification or recovery training. It directly tests whether rolling back one precision scope yields a better quality/cost Pareto point.

## Inputs and shortest executable path

- Immutable stock root: `/root/.cache/glm47flash-awq-ab31d120`, source revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Proven combined result and archive: `../full47_selective_w4_proven_path_direct/artifacts/l40s_full47_selective_w4_proven_path_20260716_r1/`, archive SHA-256 `58349e47b405ae7f62645be89aa0b9c256de1c6082b1671ad64a69a5185c2a72`.
- Proven official producer: `../full47_official_selective_w4_cuda_endpoint/materialize_official_roots.py`, using compressed-tensors `PackedQuantizationCompressor`, symmetric group-32 `uint4b8`, and the pinned MSE scale search.
- The materially complete but unadmitted shared-only root is `/root/.cache/official-full47-official-shared-w4-bf16-head-nd9n5e_5`: 138 BF16 shared tensors become 414 packed/scale/shape tensors, `lm_head.weight` remains BF16, weight bytes are `19,546,203,552`, and the observed manifest hash is `dabfe16175fb282e72def9606ccaf0479c14dd09f1e25688c6e54cb9c405ebfa`. Treat it as a candidate until the final content-address and admission pass.
- Materialize one head-only root with the same official producer: exactly one BF16 `lm_head.weight` becomes three packed/scale/shape tensors, all shared and unrelated tensors remain byte-identical, and expected weight bytes are `19,714,233,744`. Do not use or repair the quarantined custom-nibble roots.
- Proven provider lifecycle: `campaign_100/nebius/vllm_smoke_control.py`, `vllm_recover_existing.py`, and the shared `placement_control.VerifiedRetainedOwner` terminal guard on Nebius L40S.

Extend the existing official producer, binder, and CUDA oracle only enough to select `head_only` versus `shared_only`. Before create, require exact scope/index/config closure, official pack/dequant agreement, finite bounded numerical evidence, no BF16 duplicate for the selected scope, unrelated tensor-byte identity, the real checkpoint staging admission, and scope-aware actual-runtime fixtures. The head-only primary uses the existing narrow `ParallelLMHead` WNA16 selector. Shared-only must use native `Linear` WNA16 and keep the ignored BF16 head; it must not invoke or depend on the head adapter.

In the same project and before create, make the existing quality path retain serialized raw API response bytes, normalized responses, their one-to-one hashes/identities, and the exact scorer output. Pass one representative raw response through the actual serializer/normalizer/scorer consumer and prove that raw, normalized, suite, model, runtime, and scorer identity mutations fail closed. Do not create a new policy, suite, seal, or standalone quality project.

Run this prerequisite under one durable local owner, not a model-response deadline. Budget at most `7,200` wall-clock seconds, `16` CPU-hours, `32 GiB` RSS, `25 GiB` incremental storage, `$0`, and zero provider creates. Record its canonical unit, unit manager, absolute deadline, artifact root, and typed terminal in `STATUS.json.active_session`. Reuse the admitted head-only root. Validate the complete shared-only candidate before doing conversion again; never reuse the quarantined `_b36ckwt` temporary root. Provider creation remains forbidden until the typed terminal proves both scope roots plus all six actual-consumer mutations. A valid local owner may outlive a researcher response and must not be killed or restarted because the response ends.

## Director reactivation after the pre-create close

The prior `PRECREATE_SCOPE_PACKET_NOT_EXECUTABLE` result is superseded as an admission decision, not erased as evidence. The missing head-only packet and stale shared-only head dispatch were the implementation work assigned by this project, so their absence was not a scientific endpoint. Shared tooling now has a scope-aware producer, binder, CUDA oracle, and main-launcher flag, but the paid path remains gated on the following concrete corrections in this same project:

- make the scope universe exact: `lm_head.weight` plus layers 1–46 `shared_experts.{gate_proj,up_proj,down_proj}.weight`; reject count-preserving fake names;
- require exact group-32 symmetric W4 args, native `Linear` targeting for shared weights, no `ParallelLMHead` target under `shared_only`, no unselected packed tensors, and no selected BF16 duplicates;
- add bounded pack/dequant numerical admission for every selected isolated tensor, not finiteness-only sampling;
- validate the content-addressed checkpoint against the requested scope before provider create, and reject isolated W4 in BF16-v2 mode;
- propagate `head_shared_w4` and `selective_w4_scope` through `vllm_recover_existing.py`, staging and running the same binder/oracle for the retained shared-only arm;
- add execution-path tests for wrong-root rejection, exact-geometry/native-Linear mutations, binder/oracle closure, and retained recovery scope propagation;
- extend the existing AWQ batch path to retain per-response raw bytes, canonical normalized rows, one-to-one binding rows, exact scorer output, and an identity manifest over suite, checkpoint/model, runtime, normalizer, scorer, and BF16-control identities; mutation-test all six required identity classes through the actual consumer.

Admit the retained `head_only` root and validate or materialize `shared_only`, execute their admission, and finish the raw-quality bridge under the bounded local owner. Missing propagation or capture support is assigned work and is not a response-bound stop condition. Close locally only on the typed local owner's resource-bounded terminal. On pass, launch the already-authorized provider owner without a support successor. Do not split this into a packet, seal, controller, or successor project.

## One sequential allocation

Authorize one preemptible Nebius L40S create, no retry, at most `3,000` allocation seconds and `$0.72` actual exposure. Use one sequential owner wrapped around the whole sequence by `VerifiedRetainedOwner` plus one independent instance/disk watchdog. The owner must exercise its real typed summary, true/false trigger, insufficient-reserve, raw-quality-artifact, and cleanup-failure paths before create. Terminal success requires the final typed scope decision and fresh authenticated zero instance/disk inventory.

Run head-only W4 first at c16 and c32 with cache off, BF16 KV, four KV splits, max-seqs 32, 65,536 batched tokens, exact 8,192 input / 1,024 output requests, and a 300-second background envelope. Record complete rows and token streams, serialized raw quality captures and exact scoring lineage, semantic identity, cache-disabled/zero deltas, throughput, TTFT/TPOT/queue, peak and steady HBM, utilization/power/clocks, useful GPU seconds, actual exposure, archive hashes, and cleanup state.

Because measured create, SSH, runtime bootstrap, and first checkpoint staging (`873.778 s`) materially exceed scored GPU time, preregister exactly one adjacent follow-up: `VALID_HEAD_ONLY_ENABLES_SHARED_ONLY_SCOPE`. It is true only after a typed head-only full-load endpoint with complete c16/c32, semantic/cache evidence, complete identity-bound raw quality artifact, the shared-only packet prepared offline within ten minutes, and at least `1,250 s` remaining. On true, reuse only the verified content-bound runtime, fully restage and verify the content-bound shared-only checkpoint with `vllm_recover_existing.py --reuse-staged-runtime` (never `--reuse-staged-runtime-and-checkpoint`), then run shared-only c16/c32 and clean. No head-only checkpoint state may leak into the shared-only arm. On false or insufficient reserve, clean immediately.

Do not run combined W4 again, stock again, split-8, c36, a third precision scope, training, holdout, broad evaluation, or another provider session.

## Decision

For each valid isolated scope, report architecture-cost status at c32:

- robust at `>=606.355` output tok/s;
- economic in `[594.466,606.355)`;
- performance close below `594.466` or with `<512 MiB` conservative HBM headroom.

Separately report the bounded development-quality signal. A scope is `QUALITY_SIGNAL_PLAUSIBLE` only if the fresh raw-bound exact consumer shows no negative overall point regression versus its BF16 control, no critical or catastrophic category regression, and the prospective NLL ceiling passes. This is candidate-specific development localization, not quality eligibility, holdout certification, deployability, or a provider-beating claim.

Use the existing combined result plus the two isolated scopes to classify:

- head-only plausible / shared-only fail: preserve head-only and implicate shared quantization;
- head-only fail / shared-only plausible: preserve shared-only and implicate head quantization;
- both plausible while combined fails: interaction close; preserve the faster isolated scope;
- both fail: isolated-scope quality close; do not open another W4 precision ablation;
- only one valid endpoint: preserve that result narrowly and leave the other scope unresolved without retry.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/sol/experiments/glm47flash/campaign_100`
