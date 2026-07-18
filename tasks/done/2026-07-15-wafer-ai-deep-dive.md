# Task: 2026-07-15-wafer-ai-deep-dive

## Outcome

A source-backed review identifies what Wafer's full-stack and AMD work demonstrates, its disclosed inference suppliers and product launch strategy, what is reproducible, and which minimal research-factory and hosting decisions follow for GLM-4.7 Flash and GLM-5.2.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/19
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-15T12:28:24+00:00
- started: 2026-07-15T12:28:24+00:00
- last updated: 2026-07-15T12:28:24+00:00
- scope: research/sol/docs/WAFER_AI_FULL_STACK_DEEP_DIVE_2026-07-15.md,research/sol/docs/WAFER_AI_PRODUCT_AND_INFRASTRUCTURE_REPORT_2026-07-15.md,.agents/skills/research-director/SKILL.md,research/sol/experiments/glm47flash/research_lab/CAMPAIGN.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: Wafer's public work can sharpen the lab's full-stack opportunity search without adding orchestration complexity.
- acceptance checks: primary-source case studies, independent market check, public-artifact audit, disclosed supplier map, product/launch requirements, model-scoped implications, and concise director/campaign adoption.
- quality gate: distinguish first-party, independent, derived, and inferred evidence; do not transfer results across models or hardware.
- SLO or budget: research only; no paid experiments or external mutations.
- timeout: one research turn.
- artifact locations: `research/sol/docs/WAFER_AI_FULL_STACK_DEEP_DIVE_2026-07-15.md`, `research/sol/docs/WAFER_AI_PRODUCT_AND_INFRASTRUCTURE_REPORT_2026-07-15.md`
- resume command: read this task and the deep-dive artifact, then run the repository checks.
- rollback or cleanup: revert only the three scoped research/skill files; release this task claim when verified.

## Plan

1. Inspect Wafer's product, technical case studies, infrastructure disclosures, and public artifacts.
2. Cross-check current endpoint claims, suppliers, and evidence limitations.
3. Write the durable research and product reports and adopt only concise, high-leverage lab guidance.

## Result

- status: done
- verification: research-director skill validation, `python3 tools/devex/check.py`, and `git diff --check` pass.
- changed paths: `research/sol/docs/WAFER_AI_FULL_STACK_DEEP_DIVE_2026-07-15.md`, `research/sol/docs/WAFER_AI_PRODUCT_AND_INFRASTRUCTURE_REPORT_2026-07-15.md`, `.agents/skills/research-director/SKILL.md`, `research/sol/experiments/glm47flash/research_lab/CAMPAIGN.md`
- limitations or blocked paths: Wafer does not publish model-to-provider routing, supplier traffic shares, capacity contracts, or its private serving stack. The historical local branch tooling conflicted with unrelated direct commits, so this scoped work was not committed rather than mutating shared branch state.
- commit: uncommitted local worktree
- next action: finish the GLM-4.7 measured result, then obtain matched production quotes from TensorWave, Vultr, DigitalOcean, Nebius, and other finalists using the report's due-diligence contract.
- released: 2026-07-15T12:47:45+00:00
