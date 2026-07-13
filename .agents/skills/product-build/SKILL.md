---
name: product-build
description: Build and verify product changes from repository inspection through implementation, tests, documentation, and durable handoff. Use when an agent is asked to prototype, implement, improve, or ship a product or developer tool while keeping the repository as the complete project state.
---

# Product build

Move from intent to a tested, reviewable repository change.

## Workflow

1. Inspect the repository, current status, nested instructions, existing interfaces, and the nearest tests before designing.
2. Translate the request into a small behavior contract: user, input, output, failure behavior, persistence, and acceptance checks.
3. Choose the smallest change that fits existing architecture. Reuse local tools, fixtures, and conventions before adding dependencies.
4. Write or update a failing behavioral test when practical, implement the minimum change, then refactor.
5. Verify the narrow path first, then the relevant workstream checks. Report missing tools separately from code failures.
6. Update the durable README, handoff, schema, or decision record so another agent can resume without conversation history.

## Repository rules

- Keep source, configuration, prompts, test fixtures, generated decision artifacts, and run instructions in the repository.
- Keep only credentials, cookies, and private external state outside it.
- Do not introduce a SaaS board or external document as required project state.
- Preserve user changes and do not commit or push unless explicitly requested.
- For research-facing features, label measured versus modeled behavior and include a reproducible command.

Use [build-handoff.md](references/build-handoff.md) for the completion record.
