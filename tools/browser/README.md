# Repo-local browser runtime

This directory is the home for browser research and product UI checks. Keep dependency declarations, scripts, browser policies, and reproducibility metadata here. Keep browser profiles, cookies, downloads, screenshots from authenticated sessions, and transient logs under `.agents/runtime/`.

The preferred stack is:

1. Browser Use CLI for agent-oriented navigation when a task needs interaction.
2. Playwright for deterministic tests, extraction, screenshots, and replayable flows.
3. The built-in web tools for ordinary public-source research when interaction is unnecessary.

Create the environment from the repository root with `uv sync --project tools/browser`, then install only Chromium with `uv run --project tools/browser playwright install chromium`. Do not use a personal Chrome profile or expose a remote debugging port publicly.

Before an authenticated or state-changing task, stop for a human checkpoint. Browser credentials and cookies must remain outside Git and outside shared agent artifacts.
