# H200 W4 component price hurdle

## Question

Does H200 execute the proven checkpoint-free Gemma 4 W4 Machete linear plus actual `ParallelLMHead` component stack at c128 or c96 at least 1.160714286× faster than the matched H100 rows, enough to offset its committed-production price premium?

## Why this matters

The W4 H200 endpoint route reached exact-image model load and repaired server readiness but exhausted 8,069.201 cumulative provider seconds without retrieving a request row. Another full checkpoint transfer would repeat an operationally exhausted route. The successful H100 component frontier already supplies matched, numerically valid consumers and a direct hardware-placement comparator, so a checkpoint-free H200 replay is the shortest experiment that can falsify whether H200 remains economically interesting.

## Bound evidence

- Model: `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`.
- Matched H100 terminal: `../h100_w4_background_concurrency_frontier/artifacts/gemma-h100-w4-frontier-20260717t22121784319137z/RECONCILED_FRONTIER_TERMINAL.json`, SHA-256 `63c3fa9dba6999926e663d229b96902b72d1e1d809a8664f37baedc332682c7e`.
- H100 c128 combined W4-plus-head: `0.057100911377696316` seconds/request; H200 must be at or below `0.049194631328675076`.
- H100 c96 combined W4-plus-head: `0.07381828800945853` seconds/request; H200 must be at or below `0.06359729426941725`.
- Source program identities and provider placement are mechanically bound in `BINDINGS.json`.

## Scope

Use one mutable retained H200 development owner and the proven checkpoint-free H100 frontier programs. Change only placement-specific lifecycle/configuration needed for H200; repair ordinary imports, paths, runtime context, API, telemetry, or first-call defects in place. Run the existing numerical sentinel, then matched W4 and actual-head rows at c128 and c96. Preserve cold/warm metadata and authenticated cleanup.

Do not transfer the 19.22-GB checkpoint, launch a full endpoint, rerun c48/c64, add an audit/readiness project, or infer attention, KV, prompt, endpoint, quality, or production eligibility. This project answers only the price-normalized component-placement question.

## Decision rule

H200 survives only if all actual consumers and numerical oracles pass and at least one matched concurrency meets its exact H200 threshold. Otherwise close H200 W4 component placement. A survivor may justify a separately budgeted endpoint geometry only after this project finishes; it does not itself establish end-to-end economics.

## Resources and limits

- Profile: execution.
- Hardware: one H200 SXM, preset `1gpu-16vcpu-200gb`.
- Wall clock: 45 minutes.
- Provider exposure: 30 minutes / 0.50 H200-hours.
- Storage: one 100-GiB disk; 2 GiB retrieved artifacts.
- Spend: $1.50 maximum at the bound experimental rate.
- Owner: one retained development session with absolute watchdog, repair lease, durable phase artifacts, and authenticated cleanup.
