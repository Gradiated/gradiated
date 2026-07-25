# Task: 2026-07-25-sota-inference-lab-tools

## Outcome

Researchers have an optional, documented instrument shelf for matched endpoint
replay, first-divergence localization, exact-shape reproduction/evaluation,
hot-operation replacement, model-surgery experiments, warm workspaces, and
upstream tool discovery. The existing harness remains the only scheduler.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/27
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-25T21:13:14+00:00
- started: 2026-07-25T21:13:14+00:00
- last updated: 2026-07-25T21:13:14+00:00
- scope: research/factory/src/grad_research/science_tools/,research/factory/tools/lab-*,research/factory/tests/test_science_*.py,research/factory/data/tool_catalog.json,research/factory/SCIENTIFIC_TOOLS.md,research/sol/docs/AGENTIC_INFERENCE_LAB_SOTA_CAPABILITY_PLAN_2026-07-25.md,.agents/skills/research-director/SKILL.md,.agents/skills/researcher/SKILL.md,.agents/skills/research-supervisor/SKILL.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: reusable instruments will shorten repeated setup,
  observer, parser, divergence, and integration work without constraining agent
  scientific judgment.
- acceptance checks: focused unit tests pass; every CLI has useful `--help`;
  offline fixtures exercise paired comparison, divergence, reproducer/evaluator,
  replacement, surgery, workspace, and catalog paths; role skills present the
  tools as optional.
- quality gate: deterministic tools retain identities, raw evidence, and typed
  errors; they never infer a scientific conclusion.
- SLO or budget: no provider spend; no new daemon, scheduler stage, database
  service, mandatory profiler pass, or standing third-party dependency.
- timeout: one implementation turn.
- artifact locations: `research/factory/src/grad_research/science_tools/`,
  `research/factory/SCIENTIFIC_TOOLS.md`, and focused tests.
- resume command: `PYTHONPATH=research/factory/src python3 -m unittest discover
  -s research/factory/tests -p 'test_science_*.py' -v`
- rollback or cleanup: remove the optional `lab-*` wrappers and skill pointers;
  no campaign state, GPU lifecycle, or provider resource is mutated.

## Plan

1. Implement small artifact/schema primitives and independent scientific tools.
2. Document a decision map and expose the tools through existing role skills.
3. Exercise offline end to end, run factory and DevEx checks, then review for
   process bloat and commit only task-owned paths.

## Result

- status: done
- verification: 56 focused science-tool tests and 221 complete factory tests
  pass; all wrappers compile, expose help, and are executable; DevEx checks
  pass; two skeptical design reviews, one cold-start forward test, and a final
  adversarial audit informed evidence-validity, secret-safety, and
  documentation fixes.
- changed paths: new `research/factory/src/grad_research/science_tools/`
  package, seven `research/factory/tools/lab-*` wrappers, focused tests, tool
  catalog, operator guide, architecture report, and concise role-skill links.
- limitations or blocked paths: tools are optional and provider-neutral; no
  GPU was provisioned and no third-party route bundle was installed. Project
  attachment was unavailable to the fine-grained GitHub token, so issue #27
  is canonical without a GitHub Project field.
- commit:
- next action: use the optional instruments on the next suitable live research
  lineage and extend them only where measured researcher friction justifies it.
- released: 2026-07-25T21:58:03+00:00
