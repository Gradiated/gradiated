# Next experiments: measured GPU co-design campaign

Status: proposed 2026-07-12  
Scope: RunPod-backed validation of the Fable/Sol research program

## Objective

Replace the current analytical and component-level claims with one reproducible,
end-to-end measured result:

> Does one model-specific intervention lower fully loaded inference cost while
> preserving quality, latency SLOs, and serving reliability against a tuned
> commodity baseline?

The first pass must be a falsification campaign, not a provider launch. It must
produce evidence that can enter Sol's claim-composition and predictive-validity
gates.

## What we are carrying forward

Fable supplies the candidate mechanisms:

- custom serving and scheduling with less framework overhead;
- selective low-bit weights, especially the `o_proj`/`gate_proj`/`up_proj`
  mask that passed the current Qwen3-0.6B proxy quality gates;
- architecture-specific packed kernels;
- KV precision and prefix-cache policy;
- model-specific batching and prefill/decode scheduling.

Sol supplies the admission rules:

- no simulated effect may be converted into dollars per token before calibration;
- small-model evidence does not transfer to GLM-5.2 without a fresh GLM test;
- component speedups are not end-to-end speedups;
- every candidate needs an exact pinned model, workload, implementation,
  quality suite, SLO contract, and provenance record;
- the business gate is at least **1.5x lower measured cost** with non-inferior
  quality and all SLOs met;
- custom silicon remains out of scope unless the commodity result survives on
  two models with substantial residual benefit.

## Phase 0 — freeze the experiment contract

Before renting a GPU, commit the following identities and files:

1. Model revision and SHA-256 fingerprints.
2. Baseline runtime, CUDA, driver, PyTorch, Transformers, vLLM/TensorRT-LLM
   or custom-kernel revisions.
3. Candidate transformation and exact tensor mask/config.
4. Quality corpora and prompts, including the existing 512/4,096-target
   teacher-forced suites and exact-source PIQA subset.
5. Workload trace: start with
   `research/lab/experiments/workloads/aa-agentperf-public-proxy-v1.json`.
   Keep it explicitly labelled synthetic until replaced by a privacy-safe
   measured trace.
6. Two serving regimes:
   - short-context / low-concurrency: 2K–8K input, C1–C8;
   - agentic / long-context: 32K–131K input, C16–C64.
7. Predeclared metrics, pass/fail thresholds, and maximum budget.

Every run must emit a content-addressed result containing the full software,
hardware, model, workload, and git state. No manual numbers should be copied
into the economics model.

## Phase 1 — GPU sanity and tuned baseline

**GPU:** RTX 4090 Community, one GPU.  
**Purpose:** establish a cheap CUDA baseline and make the harness work.

Run Qwen3-0.6B in BF16 or the strongest supported baseline format. Compare at
least:

- batch 1 and saturated batch;
- cold start and warm steady state;
- fixed prompt lengths and the public agentic trace;
- baseline serving runtime versus the simplest available custom path.

Record:

- prefill and decode throughput;
- TTFT, TPOT, end-to-end latency and p50/p95/p99;
- request goodput by SLO class;
- GPU utilization, memory, temperature, power and clock state;
- failures, timeouts, OOMs and restarts;
- input/output tokens and Pod seconds for cost accounting.

The baseline is invalid if the GPU is not thermally stable, the process is
contended, the model hash changes, or any request is silently dropped.

RunPod's currently listed Community rate is approximately $0.34/hour. Keep the
first run short and terminate the Pod immediately after artifact upload.

## Phase 2 — selective INT4 full-model test

**GPU:** RTX 5090 Community or L40S Community.  
**Purpose:** test whether the passing Qwen selective INT4 representation is
useful beyond teacher-forced quality and scalar component kernels.

Candidate:

- group-8 selective quantization of `o_proj`, `gate_proj`, and `up_proj`;
- retain the current BF16-scale representation first;
- implement real packed storage and a CUDA kernel;
- keep the unmodified BF16 model as the exact control.

Required comparisons:

1. tuned BF16 production kernel/runtime;
2. packed INT4 candidate with the same scheduler;
3. candidate with and without any fused kernel optimization;
4. batch and context sweeps, not only batch 1.

The existing 4.457x NEON component result is a hypothesis about implementation
headroom, not a prior for full-model throughput. The primary result is full
model goodput under the same SLO, not the inner-loop ratio.

Promote only if all quality gates pass, task-level quality is non-inferior, and
the candidate improves measured cost or goodput after all overheads. A byte
reduction without a runtime or cost benefit is a negative result.

Approximate current Community rates: RTX 5090 $0.69/hour; L40S $0.79/hour.

## Phase 3 — serving and scaling test

**GPU:** A100 80GB Community, one GPU initially.  
**Purpose:** test the interaction between representation, memory pressure,
batching, prefix reuse and scheduling on a larger model.

Start with Qwen3-8B only after Phase 2 is reproducible. Test the exact paired
control/candidate intervention, then add the smallest useful serving ablations:

- prefix cache off/on;
- packed versus unpacked KV where supported;
- prefill packing off/on;
- continuous batching and concurrency sweep;
- short versus long context;
- cold versus warm cache.

Do not combine several candidate interventions in the first run. The causal
question must remain attributable to one change. A100 PCIe is currently listed
around $1.19/hour Community.

## Phase 4 — predictive-validity campaign

The current Sol gate has only one prospective component pair and fails its 15%
effect-error limit. Rebuild it around GPU measurements:

- at least three interventions;
- at least two context/concurrency regimes;
- one predeclared regression;
- calibration cases disjoint from holdout cases;
- predictions locked in git before the timed holdout runs;
- exact artifact identity checks after measurement.

Candidate intervention set:

1. selective INT4 packed weights;
2. prefix-cache policy or prefill packing;
3. a deliberately negative control, such as global INT4 or the rejected
   one-shot KV-head merge.

Pass the promotion gate only if the effect error is at most 15%, rank
correlation is at least 0.8, and the quality/SLO gates are exact. Directionally
correct but badly sized predictions remain useful research, but cannot feed
the economic model.

## Phase 5 — GLM-5.2 screening, only after calibration

**GPU:** H100/H100 NVL, only for a narrowly scoped native-checkpoint test.  
**Purpose:** determine whether a surviving mechanism transfers to the actual
target family.

Use GLM-5.2 native geometry and the public agentic proxy to select the workload;
do not transfer Qwen3-0.6B or Qwen3-8B throughput numbers. Start with one
incumbent-grade control and one intervention, such as:

- native/available FP8 or selective NVFP4 baseline;
- model-specific route placement or cache policy only if the exact checkpoint
  and runtime expose the required action;
- measured P/D or MTP only if acceptance and transfer work are observable.

Measure the complete contract: task quality, agent success, TTFT/TPOT/E2E SLOs,
throughput, cache/transfer traffic, power, failures, availability and fully
loaded cost. H100 is currently listed roughly $2.59–$2.69/hour Community.

Do not call this a business result from a roofline, device-count screen,
vendor-reported throughput, or a partial component benchmark.

## Cost and operating rules

- Create one short-lived Pod per clean experiment or one immutable image with
  explicit run IDs; do not leave idle Pods running.
- Prefer Community Cloud for early falsification; use Secure Cloud only when
  reproducibility or capacity requires it.
- No persistent volume in the first smoke run. Add one only when model download
  time dominates or the checkpoint must be retained.
- Log Pod ID, GPU ID, cloud type, region, start/stop timestamps and all storage
  charges in the result artifact.
- Set a hard per-experiment budget and terminate on OOM, repeated failures,
  missing metrics or quality-gate failure.
- Keep credentials out of the repo and out of logs.

## Initial Pod configuration

The first proposed Pod is:

- GPU: `NVIDIA GeForce RTX 4090` (`gpuTypeId` exact value from RunPod MCP);
- cloud: `COMMUNITY`;
- image: `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`;
- container disk: 50 GB;
- volume: none initially;
- GPU count: 1;
- ports: only those required by the benchmark;
- name: `gradiated-qwen03-baseline`.

Creation is a billable external action and requires a final confirmation of the
GPU, image, disk, cloud and budget immediately before calling RunPod.

## Exit criteria

The campaign is successful when one exact intervention has:

1. reproduced from a clean Pod;
2. passed the model/task quality contract;
3. met every serving SLO and reliability gate;
4. beaten the tuned baseline on the declared metric;
5. produced a measured, scope-matched cost result;
6. survived a second model or a second independently pinned regime;
7. been integrated into Sol's fail-closed evidence and claim ledgers.

The campaign is successful even if it rejects every candidate. A clean negative
result is preferable to promoting a simulated 5–10x story into a product claim.
