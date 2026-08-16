# Research log

## 2026-07-15 — alternate venue screen

- Question: Can a non-RunPod A40/A6000 path be ordered now and preserve the campaign's $0.6365/M or $0.60/M gates?
- Action: Read the existing A40 economics and queried at most three current public provider paths. Vast's official live A40 console returned no rentable instances. TensorDock's unauthenticated official inventory endpoint returned two exact A40 hostnodes; the best is one A40 in Mölln, Germany (CSN-Solutions Tier 3), listed and online, $0.33/GPU-hour, reported uptime 99.89%. Lambda's current official A6000 plan is $1.09/hour but exposes no exact public capacity.
- Observability: The isolated Playwright runtime could not launch because Chromium lacked `libnspr4.so`; this was retained as `.agents/runtime/browser-research/a40-venue-20260715/browser-diagnostic.txt` and did not determine any provider result. Direct read-only HTTP retrieval succeeded.
- Evidence: `VENUE_SCREEN_2026-07-15.json`. TensorDock's minimum 2 vCPU/4 GB/20 GB configuration makes listed cost $0.3475/hour; a conservative 10% lifecycle allowance gives $0.38225/hour, requiring 166.819 tok/s for $0.6365/M and 176.968 tok/s for $0.60/M. This is below the 266.829 tok/s preliminary screen, but no serving result is implied.
- Interpretation: TensorDock A40 is the sole qualifying conditional measurement venue and plausible production placement. It is not yet an experiment admission: local non-replicated storage, shared networking, host interruption/failure, authentication/funding, exact model load, quality, SLO, throughput, and cleanup remain gates. Vast is closed on availability; Lambda is closed on economics.
- Next move: after provider-adapter admission and campaign quality authority permit, re-read TensorDock inventory and run one exact-load matched c8 A40 measurement. No provider mutation or spend occurred in this turn.
