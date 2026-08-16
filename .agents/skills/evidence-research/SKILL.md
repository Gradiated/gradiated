---
name: evidence-research
description: Conduct source-backed, falsifiable technical, product, market, or literature research and leave a reproducible, uncertainty-labeled artifact in the repository. Use when an agent must investigate a question, compare alternatives, review a paper or vendor claim, or produce a decision brief.
---

# Evidence research

Turn an open question into an auditable repository artifact.

## Workflow

1. Define the decision, the exact claim being tested, the scope, and what would falsify it.
2. Read the relevant workstream report, handoff, and nested agent instructions before searching.
3. Prefer primary sources and current official documentation for unstable facts. Record source URLs, revision or publication date, retrieval date, and the evidence type.
4. Separate measured, analytical, vendor-reported, derived, inferred, and synthetic evidence. Do not combine them into a stronger claim than the weakest link permits.
5. Record competing explanations, missing controls, uncertainty, and negative findings.
6. Save the result in the relevant repository workstream. Update its durable handoff or ledger when the result changes the next decision.

## Workstream routing

- For `research/lab`, read `README.md`, `CONTEXT_HANDOFF.md`, and `AGENTS.md`; preserve exact identity and fail-closed claim gates.
- For a new product question, create a dated decision brief or evidence record rather than an untracked note.

Use [evidence-contract.md](references/evidence-contract.md) for the minimum artifact fields. Never put credentials or private data in a source capture.
