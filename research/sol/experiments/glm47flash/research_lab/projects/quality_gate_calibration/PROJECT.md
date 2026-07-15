# Prospective quality-gate calibration

## Question

Can a prospectively frozen, executable quality screen distinguish genuine GLM-4.7-Flash capability failures from transport, normalization, reasoning-policy, and scorer defects well enough to support a quality-eligible performance claim?

## Why it matters

Quality is the campaign's immediate claim blocker. Complete BF16 and public AWQ both scored 0.3333 on the six-case development screen, while otherwise identical stock arms scored 0.1667 and 0.3333 when a correct retrieval answer gained an extra prefix. Tool-call and serving cases were marked malformed, coding scored zero, and the NLL ceiling is uncalibrated. Paired AWQ non-regression is useful but cannot replace an absolute eligibility gate.

## Relevant evidence

- `campaign_100/quality/`, especially `development.jsonl`, `holdout.jsonl`, `policy.json`, and the runner/scorer code.
- `campaign_100/allocations/nebius_l40s_vllm_awq_batch_v19/summary.json` and the V24R1/V24R2 quality artifacts.
- `campaign_100/DECISION_CONTINUE_NARROWLY_SPLIT8_STOP_2026-07-14.json` and opportunity `OPP-007`.
- Measured current result: BF16 and AWQ each score 0.3333; AWQ NLL 7.6300 versus BF16 7.6455; the current absolute point screen fails.

## Scope

Work prospectively and start with zero-cost local analysis and tests. Audit archived raw responses through each transport/parser/scorer boundary, create discriminating executable fixtures and mutation controls, and design a larger development suite with a disjoint holdout and explicit uncertainty policy. Preserve provenance and content identities. Do not edit or reinterpret the frozen current gate, disclose or tune on the existing holdout, run performance experiments, or change serving/kernel code. New model generations, if ultimately necessary, require a separate bounded preregistration after the offline audit identifies exactly what evidence is missing.

## Available resources

The shared factory tools, `campaign_100/quality`, workload/tokenizer fixtures, archived response bundles, and existing Python tests are available. No paid GPU allocation is authorized by this brief's first stage.

The complete-V13 suite and preregistration are scientifically ready, but the admitted run correctly stopped before spend because neither the lifecycle canary nor the historical V1 stock runner can execute the new 36-case capture and artifact contract. Revoke paid/provider authority for this cycle. Implement one bounded zero-provider durable V2 capture controller by composing the proven external systemd ownership/watchdog boundary with the exact suite, V13 identity checks, three fresh server-process phases, raw/normalized/transform/logprob retention, terminal result, and two-view cleanup contract. Require a fake/local end-to-end terminal proof and fail-closed identity, missing-artifact, timeout, and cleanup controls. Do not redesign the suite, access the holdout, launch a model, mutate a provider, or spend the conditional $4.27. A passing controller proof earns a later fresh admission; another readiness-only turn does not.

## Portfolio-changing result

A calibrated control that passes a prospectively frozen screen, together with a defensible paired policy for AWQ, unlocks quality-adjusted serving comparisons. Evidence that the intended BF16 control genuinely fails critical categories redirects the portfolio to serving/parser correctness or stops business claims before more optimization spend. An audit that cannot separate scorer defects from capability failures keeps all economic claims blocked.
