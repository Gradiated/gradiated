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

The admitted run's actual-adapter preflight failed closed at $0: inventory and the 48-shard V13 checkpoint are valid, but no implementation connects the fake V2/systemd proof to the real Nebius H100 lifecycle and exact capture contract. Apply the preregistered stop rule. Pause this project, revoke provider/spend authority, and do not assign another controller, adapter, readiness, or admission cycle. Preserve the sealed holdout and all artifacts. Reopen only by a later portfolio-level decision that supplies an already implemented and independently reviewed actual adapter; building one is no longer delegated by this lab.

## Portfolio-changing result

A calibrated control that passes a prospectively frozen screen, together with a defensible paired policy for AWQ, unlocks quality-adjusted serving comparisons. Evidence that the intended BF16 control genuinely fails critical categories redirects the portfolio to serving/parser correctness or stops business claims before more optimization spend. An audit that cannot separate scorer defects from capability failures keeps all economic claims blocked.

## Director admission — Cycle 25

The portfolio-level prerequisite is now supplied: `bf16_v2_actual_adapter` implements the real H100 backend, pinned-container 36-case remote capture, explicit mutation switch, content-bound artifacts, and two-view instance/disk cleanup, with the final host-without-SGLang fixture passing. Reopen this project as sole provider owner for the frozen three-capture intended-BF16 calibration.

Use `/root/workspace/research/sol/experiments/glm47flash/research_lab/projects/bf16_v2_actual_adapter/actual_adapter.py --mutate` with local model `/root/.cache/glm47flash-bf16-33faccf4`, this project's `BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json`, `executable_development_v2/MANIFEST.json`, the adapter's `remote_v2_capture.sh`, and the already matched SSH key/public-key pair. The immutable model, suite, runtime image digest, endpoints, three 900-second cold-start captures, 3,600-second scientific deadline, scorers, and sealed holdout do not change.

Before create, group only mutable checks: direct empty instance/disk inventory, current H100 orderability, key pairing, and availability of the pinned image/local files. Apply exactly two known shared lifecycle mechanics if the adapter does not already contain them: persist/redact create stdout/stderr and reconcile the exact named resource after a contradictory nonzero Nebius exit; launch the proven independent instance/disk watchdog before SSH/model work. Those corrections and the first capture must occur in the same researcher turn—no readiness-only handoff.

Run captures 1, 2, and 3 on the resident verified checkpoint, retrieve and validate every raw/logprob/normalized/identity artifact before cleanup, freeze the six sequence NLL ceilings from the three BF16 means, and apply the preregistered category gate. Any identity, container, raw-evidence, timeout, provider, or cleanup failure stops; holdout, AWQ generation, and performance work remain prohibited. Scientific deadline is 3,600 seconds, watchdog deadline 3,900 seconds, and total spend cap is $4.27 including cleanup.

## Director readmission — Cycle 26

The V34 lineage is terminal, cleaned, and scientifically null. Nebius created the named H100 and disk, but the adapter failed before SSH because `NebiusBackend.address()` called the imported historical `wait_ssh` primitive without its required SSH-key argument. `actual_v13_capture_run/adapter-error.json` records the `TypeError`; `terminal-result.json` contains zero phases and verifies direct and inventory absence for both instance and disk. The service existed for about 115 seconds, so no model, capture, or quality inference is admissible.

Admit one fresh V35 attempt in this same project because this is a bounded call-contract defect rather than evidence against the checkpoint, suite, runtime, provider, or quality hypothesis. Do not create another adapter or controller. First patch the existing `/root/workspace/research/sol/experiments/glm47flash/research_lab/projects/bf16_v2_actual_adapter/actual_adapter.py` call to match the imported `wait_ssh(ip, key, deadline)` contract and add a focused actual-backend address regression that would have failed V34. Also complete the two lifecycle mechanics already required by Cycle 25 if they are still absent: persist/redact create diagnostics with exact-name reconciliation after a contradictory nonzero create exit, and arm an independent instance-plus-disk watchdog before create. Run the focused tests, then launch V35 in the same researcher turn through the same absolute adapter/model/spec/suite/remote-script/key paths. No readiness-only handoff is admissible.

The cumulative V34+V35 spend ceiling remains $4.27; conservatively authorize at most $4.14 additional spend after the failed service interval. V35 retains the 3,600-second scientific deadline and 3,900-second external deadline. Run the same three captures and gates. Any further pre-GPU adapter/controller defect, or any provider, identity, model, artifact, scientific-timeout, or cleanup failure, closes this quality-capture route without another retry. Holdout, AWQ generation, and performance work remain prohibited.

## Director terminal decision — Cycle 30

V35 is terminal and the quality-capture route is closed. After the complete checkpoint transferred, capture 1 failed before container start because Docker could not create the bind-mount target `/input/remote_v2_capture.sh` on the read-only `/input` filesystem. `actual_v13_capture_v35/terminal-result.json` records zero phases and verified direct-plus-inventory absence of both instance and disk. Do not patch or retry this adapter, create a successor quality controller, generate/access the holdout, or spend against the former H100 authority. Preserve the frozen suite and terminal evidence for a later portfolio-level route that arrives already executable; this project is complete without a quality result.
