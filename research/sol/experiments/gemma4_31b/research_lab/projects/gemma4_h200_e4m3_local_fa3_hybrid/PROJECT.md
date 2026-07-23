# Local E4M3-FA3 / global E5M2-Triton hybrid on H200

## Question

After the layerwise mixed-KV project establishes a scope-matched comparator, can Hopper FA3 replace Triton only on Gemma 4's 50 local head-dim-256 layers while all ten global head-dim-512 layers remain E5M2 Triton?

## Evidence and changed scope

Iteration 1 completed the pinned-source router, producer/consumer trace, and bounded runners, but correctly spent no GPU arm because its required uniform-E4M3 comparator closed at `0.7022842786 s/request`, 4.146% slower than the E5M2 control and without retained QKV audit events. Uniform E4M3 and that dependency contract remain closed.

This iteration is materially different: local layers alone use E4M3 so FA3 can consume them; global layers remain on the production E5M2 representation and Triton backend. The direct dependency `gemma4_h200_layerwise_mixed_kv_endpoint` measures that exact mixed-format stack first. The prior source binding already identifies `SWAKVPool`, the paged pool, scales, layer geometry, and a 50/10 backend router; reuse it as historical implementation evidence, then rebind the live mixed-pool producer and consumers.

The measured local-attention wall fraction is `0.1531203203`. Against the persisted E5M2 frontier, a 35.0744% reduction of that boundary bridges `0.6743258590` to the `0.6381105231 s/request` ceiling. The mixed comparator's measured penalty, if any, must be included before promotion.

## Immutable scope

- Exact model, checkpoint, image, runtime commit, and c32 workload are mechanically bound in `DIRECTOR_BINDING.json`.
- Local: 50 layers, 32 query heads, 16 KV heads, head dimension 256, 1,024-token window, page size one, E4M3 KV, FA3 candidate.
- Global: layers `[5,11,17,23,29,35,41,47,53,59]`, 32 query heads, four KV heads, head dimension 512, page size one, unchanged E5M2 KV and Triton.
- All weights, scales, QKV epilogue, scheduler, chunking, cache capacity, workload, and non-attention interventions remain unchanged.

## Immediate experiment

Use `$kernel-research`. Prepare offline while the priority-2500 mixed-KV project owns the bench. Adapt the existing router and component runner only for two layer-indexed pool dtypes. Bind the exact live producer, scale convention, slot mapping, graph metadata lifecycle, local FA3 consumer, and global Triton consumer.

After the dependency terminal and release, close without claiming only if mixed pools are numerically invalid or even perfect removal of their measured local boundary cannot recover the mixed penalty and beat `0.6743258590 s/request`. Otherwise claim `h200-sync-linear-e00vhh6h29fj68x91g` under a durable `$12` reservation.

Run one exact-consumer component pair on actual paged local layouts: mixed-stack local Triton versus local FA3. Require nonzero producer output, layer-correct E4M3 scales/slots, an explicit numerical oracle, stable randomized timing, no fallback, 50 local FA3 and ten global E5M2-Triton path proof, and the minimum counters needed to distinguish the predicted backend reduction. Promote to one profiler-off exact c32 candidate only if the measured component plus the dependency endpoint conservatively beats `0.6743258590 s/request`; crossing `0.6381105231` is the primary goal. Reuse the dependency terminal as control and do not replay it.

## Stop rules

Close on unsupported mixed-pool FA3 semantics, numerical failure, component regression, insufficient scope-matched bound, invalid endpoint accounting, or endpoint regression. Do not run global FA3, convert global E5M2, change the window or heads, tune FA3/Triton parameters, try another backend, or add a second candidate. A survivor is still representation-changing and requires later quality/feature validation.

## Resources

- Researcher profile: `deep`.
- One retained H200 sequentially after the mixed-KV endpoint; at most 120 claimed GPU-minutes and three wall hours from first claim.
- Project authorization: `$12.00`.
- At most 8 GiB new artifacts/build outputs; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
