# Nebius GLM GPU evidence continuation

Issue: [#11](https://github.com/joshsny/gradiated/issues/11)

Owner: primary research coordinator

Status: complete — campaign decision `CONTINUE_NARROWLY`; split-8 lineage `STOP`

## 2026-07-14 final retained split experiment and handoff

The source-pinned eight-KV-split candidate reduced exact-shape grouped-attention component time by 40.27% and reduced summed c8 attention/MLA profiler work by 33.43%. It did not materially transfer to serving. A same-session A/B/A/B/A sequence measured drift-corrected c8 throughput effects of +1.0476% and +1.0447%, median +1.0461%, versus the preregistered 5% gate. All five final arms passed semantic, exact geometry, SLO, cache, paired diagnostic, and artifact gates. With two independent candidate repetitions the result is descriptive and intentionally has no bootstrap interval or significance claim.

The matched trace-delta tool measured summed decode kernel work down 14.09% while vLLM decode annotation span changed +0.38%. Dense GEMM/GEMV is the largest residual summed family. This stops the split-count lineage and falsifies the assumption that its large component win controls the current c8 path; it does not yet prove whether the residual is dense compute, memory, launch/dependency, or host scheduling.

Cleanup passed: instance `computeinstance-e00ryn9r7gcjnecedr` returns not-found and fresh instance/disk inventories are zero. Full session exposure was 4,257.181 seconds and derived cost `$1.014772742`, bringing conservative Nebius spend to `$17.656500383/$25` and leaving `$7.343499617`. Decision artifact: `campaign_100/DECISION_CONTINUE_NARROWLY_SPLIT8_STOP_2026-07-14.json`, SHA-256 `e51b5324a7c2c28dc66122f1f5776bb898fd0573106d51311da89edf3c031131`.

Resume contract: do not test another MLA split/tile variant on this fixed workload without new critical-path evidence. First calibrate a prospective expanded quality suite off GPU. Then preregister matched profiler-off/on vLLM phase capture using Nsight Systems, available standard DCGM utilization/memory-controller/power/energy fields, host and scheduler timing, coverage, and explicit unavailable counters. Use that resource signature to admit an exact-shape dense GEMM/GEMV or MoE falsifier. No gateway work and no provider/quality-adjusted cost claim is authorized by these results.

## 2026-07-14 measurement-loop audit and V23

The campaign through V22R1 is now audited in `campaign_100/analysis/RESEARCH_HARNESS_REVIEW_2026-07-14.md` with a machine-readable cross-stack opportunity register. The retained V19-V22 session is the preferred iteration pattern, but the decisive vLLM profiler artifact was one mixed prefill/decode c1 request. Its 37.38% summed grouped-MLA kernel-duration share is diagnostic only: overlapping CUDA work and graph replay make it invalid as a c8 end-to-end Amdahl coefficient.

V23 (`664834a6...c46cc`) is preregistered as the cheapest falsifier before another checkpoint transfer. It runs 58 source-pinned grouped-MLA configurations across B1/B8 and sequence lengths 8,193 through 9,215 on one preemptible L40S, with FP32 correctness, legal-resource failures, component timing, GPU/VRAM/power telemetry, a `$0.569192` cap, artifact hashing, and verified teardown. A >=10% conservative component lead only admits a true fixed-8K/128 c8 trace; it does not admit an end-to-end or cost claim.

The reusable `$experiment-run` skill and this workstream's `AGENTS.md` now require a measurement-driven opportunity queue, broad observability, an increasingly faithful simulation/proxy ladder, residual-bottleneck measurement, prediction scoring, and one provider-state coordinator with parallel offline analysis. A reusable opportunity-ranking tool is included under `.agents/skills/experiment-run/scripts/`.

Budget update: the user explicitly authorized up to `$25` total Nebius spend on 2026-07-13. This provider-specific cap includes placement controls and inference allocations. Continue to gate spend, update the report after every allocation, and prefer same-host matched comparisons.

Placement result: v2 passed at a derived `$0.072728172`, after v1's `$0.171193495` conservative upper bound. The next preregistered allocation is `nebius_h100_stock_mtp_v1` (`a5b5e08e...fabe`): a 9,000-second / `$7.375` compute cap on a 250 GiB H100 VM. It runs the frozen stock arm first and admits the official GLM MTP/EAGLE arm on the same host only if stock passes.

Stock/MTP v1 failed closed before model download because the tested replay truncation correction was not rebound into the frozen manifest. Cleanup passed; derived cost was `$0.332601873`. The builder now binds corrected workload `d4353074...293c`, local validation runs before provider access, 104 campaign tests pass, and changed v2 is preregistered as `199c3343...0f83`.

V2 crossed exact model download but failed before server launch because the materializer used `len(BatchEncoding)` instead of `len(BatchEncoding.input_ids)`. Offline Transformers 5.12.1 reproduction matched every frozen JavaScript-derived count/hash after normalization. Cleanup passed; derived v2 cost was `$0.739477971`. Changed v3 (`9b4f87d1...29b5a`) keeps the workload identity fixed and changes only tested return-shape normalization.

V3 passed all tokenizer bindings but an inline block wrote to the legacy RunPod output path. Cleanup passed; derived cost was `$0.740797691`. Every inline path now consumes exported arm paths, regression tests limit each legacy path to its one default declaration, 104 tests pass, and changed v4 is `f3102047...20cfd`.

V4 loaded the exact model and reached a healthy stock server. Its fixed 8K/1K warmup completed, but the next append/tool request returned HTTP 400 because the tokenizer-native flat tool schema was sent directly across an OpenAI-compatible HTTP boundary. Cleanup passed; derived cost was `$0.818136755`, and the retrieved evidence archive is hash-matched at `7f30a355...9bb87`. V5 changes only the HTTP transport envelope, persists typed warmup failures, binds workload `989bfca8...375e`, and passes 105 campaign tests plus DevEx checks.

V5 passed HTTP validation and both warmups reached inference, but it exposed a transport-realistic geometry mismatch (server 252 append input tokens versus frozen 233) and two overly strict SSE parser assumptions. Cleanup passed; derived cost was `$0.811539496`, and the archive is hash-matched at `d45c0afb...7454`. No v6 allocation is admissible until actual wrapped-tool geometry is frozen and the runner observes cumulative token increments independent of delta semantics.

The exact pinned image now reproduces the full SGLang transport/tokenizer path offline: 253 rendered append tokens with hash `28e96d45...619f`, separately bound to v5's measured 252 scheduler-reported tokens. SSE timing is cumulative-token based and semantic-agnostic while retaining one-token observability. Workload `f47c7af5...193a`, tokenizer binding `ccbe405b...b14c`, 106 tests, and DevEx all pass; changed v6 is admissible.

V6 fully measured the fixed 8K/1K warmup (6.733 s TTFT, 1,023 token-level intervals, 14.650 s E2E) but proved GLM's tool parser buffers append output such that public SSE token-level ITL is structurally unobservable. Cleanup passed; cost was `$1.013695247`, archive `b7297277...f319`. The combined agent SLO gate is closed. The next admissible pivot measures fixed 8K/1K c1/c8 token SLO and separate semantic chat quality, with no agent/tool-call TPOT claim.

V7 passed the fixed c1 and c8 SLO gates; c8 measured 303.857 output tok/s and analytically implies `$2.697/M` output tokens at the `$2.95/hour` list rate. This is fixed synthetic compute-only economics, not quality-adjusted or provider-matched evidence. Quality failed closed when the first response hit the 256-token cap, so MTP was not admitted. Cleanup passed; cost was `$0.929792499`, archive `efbc68a2...ae88b`. Changed v8 explicitly disables GLM thinking only for the simple quality suite and labels that policy as tuned; MTP remains conditional on quality plus fixed SLO.

V8 reproduced c8 at 303.955 output tok/s and reasoning-off made the first two quality cases stop at 32 and 40 tokens. The frozen retrieval input is exactly 32,379 tokens, however, so the 16,384-context server rejected it before inference. Cleanup passed; cost was `$0.922553439`, archive `ad5b0d8a...0bb4`. Changed v9 sets server context to 32,768 while retaining the fixed workload, reasoning-off policy, 256-token cap, and conditional MTP gate.

V9 admitted every quality request at 32K and reproduced c8 at 304.134 output tok/s, but the absolute compact quality screen failed on strict schema/formatting plus teacher-forced NLL 7.708 versus the frozen 2.0 ceiling. Cleanup passed; cost was `$0.920819551`, archive `a9dedff6...ce41`. Do not recalibrate the observed quality gate. The next run may admit MTP diagnostically after fixed SLO, retaining paired output identity and the absolute quality failure, solely to test the model-specific decode mechanism.

V10 stopped during public model download when Hugging Face Xet CAS returned HTTP 401 after 34/52 files. No stock or MTP inference result exists. Cleanup passed and cost was `$0.671295096`. Changed v11 disables Xet and retains the v10 scientific contract; do not retry the same delivery path unchanged.

V11's standard HTTP client was redirected to a signed CAS bridge shard URL that also returned 401. Cleanup passed; cost was `$0.445960184`. The delivery lineage is stopped. Terminal decision: `STOP_OR_PIVOT`. Nebius spend is `$8.590591469/$25`; preserve the remaining `$16.409408531`. Resume only for a materially different >=3x cost mechanism or matched managed-provider control.

## Decision

Determine whether Nebius can supply a reproducible one-GPU 80 GB NVIDIA control and, if placement passes, continue the frozen GLM-4.7-Flash campaign toward a valid stock serving measurement. This provider pivot remains under the campaign's existing total authorization; it does not enlarge the scientific claim scope.

## Scope

Owned paths:

- `tasks/active/2026-07-13-nebius-glm-gpu-campaign.md`
- `research/sol/experiments/glm47flash/campaign_100/nebius/`
- Nebius-specific preregistrations and allocation artifacts under `research/sol/experiments/glm47flash/campaign_100/`
- append-only campaign/report updates attributable to Nebius allocations
- decision-relevant provider findings in `research/sol/docs/GPU_PROVIDER_AVAILABILITY_2026-07-13.md`

Do not overwrite unrelated user changes or build the gateway product.

## Read-only baseline

- Nebius CLI: `0.12.242`.
- Project: configured externally; credentials remain outside the repository.
- Active instance count: zero.
- Existing subnet count: one.
- H100 platform: `gpu-h100-sxm`, preset `1gpu-16vcpu-200gb`, 80 GB.
- Fresh capacity advice at 2026-07-13T21:12:22.281Z: regular one-GPU H100 availability of 15, 24, 15, and 2 across fabrics 2, 3, 4, and 6 respectively; tenant limit 32.
- Published unified regular H100 rate: $2.95/hour, including GPU, vCPU, and RAM; vendor-reported, not measured allocation cost.
- Remaining conservative campaign authorization before Nebius allocation: $99.726535473 based on the existing RunPod ledger. Cross-provider spend must be added rather than netted.

## Experiment 1: H100 placement smoke

### Causal hypothesis

Changing the provider control plane from the rejected RunPod Pod backend to a standard Nebius Compute VM is sufficient to allocate a regular one-GPU H100 and expose a working CUDA device over SSH within ten minutes. Expected direction: placement succeeds on an advisor-reported medium-capacity H100 fabric.

### Stock control and candidate change

- Stock control: zero active Nebius instances, authenticated platform/preset inventory, existing subnet, and fresh capacity-advisor counts.
- Candidate change: Nebius regular VM using `gpu-h100-sxm` / `1gpu-16vcpu-200gb` and an official Ubuntu CUDA image.
- This changes provider, host VM image, CPU/RAM geometry, and region. It is a placement test only and cannot be compared as serving performance.

### Identities and workload geometry

- Provider/region: Nebius AI Cloud, `eu-north1`.
- Hardware: one H100 SXM 80 GB, regular non-preemptible VM.
- Software: official Nebius Ubuntu 24.04 CUDA 13 image family if API-visible; otherwise the current official NVIDIA GPU Ubuntu image recorded before creation.
- Workload: one SSH readiness probe, `nvidia-smi` identity/telemetry capture, CUDA visibility check, and immediate teardown. No model weights or inference requests.
- Seed: not applicable; deterministic command bundle is content-hashed.

### Correctness, quality, and SLO gates

- Provider returns a VM ID and positive resource identity.
- VM becomes running and SSH-reachable within 600 seconds.
- Exactly one NVIDIA H100 with at least 80 GB is visible; no MIG slice is accepted.
- Capture driver/CUDA version, GPU utilization, VRAM, power, temperature, clocks, and failure state where exposed.
- No model-quality claim exists for this experiment.

### Budget, timeout, and cleanup

- Maximum compute exposure: 15 minutes at $2.95/hour = $0.7375.
- Absolute all-in experiment cap: $0.80, including conservative disk/IP allowance.
- Creation timeout: 120 seconds; running/SSH deadline: 600 seconds; absolute allocation deadline: 900 seconds.
- An independent local watchdog must delete the VM at the deadline.
- Delete the VM and every experiment-created disk or IP after artifact retrieval or on any failure.
- Verify subsequent instance lookup is not found and project instance inventory is empty. Verify experiment-created disk inventory is empty.

### Artifact contract

Store under `research/sol/experiments/glm47flash/campaign_100/allocations/nebius_h100_placement_smoke_v1/`:

- immutable preregistration and its SHA-256
- sanitized create request/response
- state transition timestamps
- SSH command bundle and hash
- `nvidia-smi` identity and telemetry output
- stdout/stderr and classified failure, if any
- start/end timestamps, allocation seconds, published-rate conservative cost, and ancillary-cost limitation
- remote artifact archive plus remote/local SHA-256 when a VM is reachable
- teardown requests, terminal lookup result, final instance/disk inventory, and verification status

### Acceptance and falsification

- Pass only if every correctness and cleanup gate passes.
- Falsified if an advisor-reported admissible H100 cannot be created or expose CUDA before the deadline.
- Invalid if the harness loses resource identity, misses cleanup verification, or cannot establish the selected hardware.
- Do not silently retry unchanged. A second placement may occur only with a preregistered change of fabric or H200 hardware and a separate cap.

## Verification

- Nebius driver unit tests pass without credentials or network mutation.
- Existing campaign tests remain green.
- No credential value appears in repository files or logs.
- Every allocation is appended to the ledger and `REPORT.md` before another allocation.
- `python3 tools/devex/check.py` and narrow workstream checks pass before commit.
