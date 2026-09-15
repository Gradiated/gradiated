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
6. Update an existing README, schema, or plan when behavior or operation changes. Report routine check results in the response or PR; do not create evidence folders, dated reports, or handoff files.

## Repository rules

- Keep source, configuration, reusable test fixtures, and run instructions in the repository. Keep raw test output and one-off probes under ignored `.agents/runtime/`.
- Keep only credentials, cookies, and private external state outside it.
- Do not introduce a SaaS board or external document as required project state.
- Preserve user changes and do not commit or push unless explicitly requested.
- For research-facing features, label measured versus modeled behavior and include a reproducible command.

Use [build-handoff.md](references/build-handoff.md) as a checklist for the final response or PR, not as a request to create a file.
