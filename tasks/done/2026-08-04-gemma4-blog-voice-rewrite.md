# Task: 2026-08-04-gemma4-blog-voice-rewrite

## Outcome

The Gemma 4 inference post reads like a first-rate engineering narrative rather
than a campaign report: one memorable tension, exact mechanisms, economical
evidence caveats, and a voice that is direct without becoming promotional.

## Owner and coordination

- GitHub issue: unavailable (configured token cannot resolve repository)
- GitHub project:
- owner: root
- Codex thread:
- created: 2026-08-04T08:19:38+00:00
- started: 2026-08-04T08:19:38+00:00
- last updated: 2026-08-04T08:19:38+00:00
- scope: research/sol/docs/blog/gemma4-inference-optimization
- excluded paths: all other dirty worktree paths
- dependencies:

## Contract

- hypothesis or user value: A failed-but-plausible MTP result is a stronger
  narrative spine than a flat list of wins, and will make the post memorable to
  inference engineers while preserving the positive 32% endpoint result.
- acceptance checks: revised draft passes its verifier, local links resolve,
  all performance claims remain traceable to EVIDENCE.md, and prose scan finds
  no stock AI-summary phrases or repeated templated transitions.
- quality gate: direct opening; exact benchmark denominator; at least three
  mechanisms explained through shapes/data movement; measured and unmeasured
  claims clearly separated; no unearned production or universal-quality claim.
- SLO or budget: editorial-only; no GPU spend and no new experiment.
- timeout: one working turn.
- artifact locations: `research/sol/docs/blog/gemma4-inference-optimization/`
- resume command: `python3 research/sol/docs/blog/gemma4-inference-optimization/verify_blog.py`
- rollback or cleanup: revert only the blog directory and this task packet.

## Plan

1. Review Wafer and a small set of excellent first-party industry engineering posts.
2. Rewrite the draft around one surprising result and remove report-like prose.
3. Re-run evidence, prose, link, SVG, and repository checks; record the result.

## Result

- status: done
- verification: blog verifier passed (2,901 words, three valid SVGs, claim
  guardrails); repository DevEx check passed; `git diff --check` passed; prose
  cliché scan clean.
- changed paths: `DRAFT.md`, `EVIDENCE.md`, and `verify_blog.py` in the scoped
  blog directory, plus this task packet.
- limitations or blocked paths: no new GPU work; performance scope and quality
  limitations remain those documented in `EVIDENCE.md`. Visual inspection of
  SVGs was source-based because the local image viewer could not rasterize SVG.
- commit: this task's scoped editorial commit (see git history)
- next action: editorial/design review or publication formatting.
- released: 2026-08-04T08:26:32+00:00
