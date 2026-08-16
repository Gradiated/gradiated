# Decision surface — 2026-07-17

The exact-model retail target is approximately **$0.134–$0.136 per million campaign-mix tokens** at the current low-price OpenRouter endpoints, or **$0.000614–$0.000621 per 4,214-prompt/358-output request**. The lowest fully specified cache-aware endpoint in the capture is WandB at $0.13450/M total tokens; DeepInfra FP8 is $0.13436/M when its missing cache price is conservatively charged at fresh-input price. Artificial Analysis independently reports a $0.14/M lowest 7:2:1 blend, consistent within methodology and rounding.

This does not change the L40S economic hurdle: the corrected direct arm remains the only authorized paid test, and the market target is a retail comparator rather than a self-hosting cost result. A self-hosted candidate must beat roughly $0.134/M all-in at the campaign mix after utilization, headroom, failures, storage, and orchestration—not merely GPU hourly rate.

No fallback is immediately executable. RunPod’s read-only account inventory is empty, its attempted GPU inventory path returned a documented HTTP 400 invalid-path response, and prior campaign evidence makes direct creation inadmissible. The typed fallback packet therefore contains no venue ranking. Reopen RunPod only after the active Nebius correction has a typed pre-GPU failure and verified empty inventory, and only with fresh admissible control-plane/stock evidence; do not mutate providers from this project.

Evidence: [MARKET_TARGET.json](MARKET_TARGET.json), [VENUE_FALLBACK.json](VENUE_FALLBACK.json), [OpenRouter raw capture](artifacts/openrouter-endpoints.json), [RunPod read-only capture](artifacts/runpod-readonly-snapshot.json).
