# PostHog AI agent

- **Goal:** build trustworthy analytics-agent tasks, collect useful successful/corrected traces, and test SFT and privileged-context OPD on local Qwen.
- **Scope:** one synthetic reporting-product archetype; 12 workflows; separate training, development, and final-test worlds. Task instances and execution copies are not distinct skills.
- **Results so far:** primary judge on the same 24 final tasks: base Qwen 8/24, one-epoch SFT 9/24 (inconclusive gain), procedural OPD 4/24, contract OPD 5/24, fresh Sol 21/24, DeepSeek Flash 1017 8/24. Secondary judging differs; see the timestamped [data](data/). Epoch-2/3 development evaluation is separate.
- **Conversation:** [read the transcript](traces/conversation.md) or [download structured messages](traces/conversation.jsonl): 621 visible user/assistant messages in a bounded snapshot of this T3 thread. [Activity metadata](traces/activity.jsonl) covers 2,012 tool/activity events; raw tool bodies and private reasoning are excluded. [Manifest](traces/manifest.json) records coverage, redactions, and hashes.
- **Supporting artifacts:** [data](data/), [figures](figures/), and [plot.py](plot.py). Rebuild figures with `uv run --with matplotlib python research/experiments/2026-11-02-posthog-ai-agent/plot.py`.
- **Keep recording:** use `$experiment-record` to extend the traces and keep this summary thin. No log or experiment index belongs in the top-level experiments README. Raw restricted environment data stays on fbf8; no public Site was created.
