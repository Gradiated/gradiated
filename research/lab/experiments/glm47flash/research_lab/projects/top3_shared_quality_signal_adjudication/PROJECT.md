# Top-3/shared quality-signal adjudication

## Question

Is the top-3/shared retrieval regression a genuine mutation-scoped quality signal in the completed top4/top3/top4 bracket, or an artifact of capture presentation or the exact scorer boundary?

## Why it matters

Top-3/shared clears the full-47 c32 performance gates at `644.318005` tok/s and `1.062619x` the stable control mean. Its typed development screen is not quality-eligible: `dev_retrieval_01` falls from `1` to `0`, overall score from `0.333333` to `0.166667`, and the paired CI is `[-0.5, 0.0]`. Each immutable arm archive contains raw response capture plus the exact paired-quality runner outputs, so this can be adjudicated without another evaluation or provider session.

## Scope

Work offline at `$0` for at most 600 seconds, 4 GiB RSS, and 32 MiB of new artifacts. Verify the three archive hashes and consume the representative raw captures through the exact existing runner/normalizer/scorer boundary. Bind checkpoint, runtime, config, prompt, suite, and scorer identities; compare both top-4 controls with top-3 for the retrieval case, raw response completeness, normalization, scoring, NLL, semantic result, and any nested harness error. Do not create a holdout, change policy, repair outputs, run a model, call a provider, train, or prepare a successor.

Return `QUALITY_REGRESSION_CONFIRMED` only if both controls support the retrieval behavior and the top-3 failure survives the exact boundary with complete identity-bound captures. Return `QUALITY_SIGNAL_INCONCLUSIVE` for control inconsistency or non-deterministic/presentation ambiguity. Return `QUALITY_ARTIFACT_CLOSE` if the immutable artifacts or consumer bridge are invalid. Every result preserves the inherited absolute-quality failure and makes no deployable-quality claim.

## Evidence

- `../full47_top3_shared_c32_direct/artifacts/l40s_top3_shared_c32_20260716_r1/`
- Candidate archive SHA-256 `7d232e1637cb2b7ea03f1890880598a14b26fd8cc8683b8b5723420eda77e10d`
- Pre/post archive SHA-256 `8070ea8b1bb8af12628c1f7d8fa3d1ecace82f892802ae5f9780f44e482ea765` / `b7a7a5392e3792ddfbe79412fcf3e86fce38d7d3d33154322e93c858b2c47eaf`

## What changes the portfolio

A confirmed regression blocks top-3 quality/recovery spend until a later campaign decision explicitly admits recovery. An inconclusive signal permits one future bounded quality measurement only if the sustainable-economics project leaves enough value. An artifact close invalidates quality interpretation but not the bracketed architecture-cost result.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/lab/experiments/glm47flash/campaign_100`
