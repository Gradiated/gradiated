---
name: browser-research
description: Research interactive or JavaScript-heavy websites with reproducible browser automation, evidence capture, and safe domain boundaries. Use when ordinary web search is insufficient, a page requires clicks or scrolling, a product UI needs verification, or an agent must inspect a live site without putting credentials or browser state in the repository.
---

# Browser research

Use the least powerful tool that answers the question, and make every browser result reproducible.

## Tool choice

1. Use built-in web search/open tools for ordinary public pages.
2. Use the repo-local runtime in `tools/browser/` for JavaScript-heavy pages, interaction, screenshots, and replayable flows.
3. Prefer Browser Use for agent-oriented navigation and Playwright for deterministic extraction or tests.

## Safe workflow

1. Declare the target domains, task, evidence needed, and whether the task is read-only.
2. Use a dedicated repo-local runtime and an isolated browser profile under `.agents/runtime/`; never use a personal profile.
3. Allowlist domains and rate-limit requests. Capture URL, page title, retrieval time, relevant text or structured fields, and screenshots only when they materially support the result.
4. Save sanitized, decision-relevant evidence under the relevant workstream. Keep cookies, downloads, credentials, and raw authenticated pages out of Git.
5. Stop for a human checkpoint before login, submitting forms, sending messages, publishing, purchasing, deleting, or changing account state.
6. Close the browser and report blocked pages, consent walls, bot checks, and incomplete evidence instead of silently bypassing them.

Read [browser-safety.md](references/browser-safety.md) before any authenticated or state-changing workflow.
