# Training runtime

Training recipes are selected from the canonical model catalog and frozen per run.
Qwen3 supports 0.6B, 1.7B, 4B, 8B, 14B and 32B bases on one GPU. GLM-5.3-Flash
uses the pinned BF16 checkpoint on four GPUs, eager attention and activation
checkpointing. Both use rank-two LoRA for fifty steps. The GLM path has a tiny
model CPU gradient test; full-size training and multi-GPU checkpoint recovery
still require GPU qualification. DeepSeek V4.1 training is not supported by this
Transformers runtime.
The training library is [Gradiated/autotrain](https://github.com/Gradiated/autotrain),
pinned as a submodule at `product/packages/autotrain`. It accepts explicit recipes,
local dataset/checkpoint paths and callbacks; it has no infrastructure dependencies.
This directory owns the private HTTP runtime adapter, signed artifact transfers,
container build and host lifecycle. TypeScript owns datasets, Temporal, Nomad and S3.
The base model remains loaded for training, verification and evaluation.

Initialize the private submodule before building:

```sh
git submodule update --init product/packages/autotrain
```

Build and test from the repository root:

```sh
docker buildx bake -f product/inference/bundles/build.hcl verify-training
```

The build installs the Python package from the pinned checkout, with dependencies
locked by this runtime. CI fetches that exact commit using a read-only deploy key
stored as `AUTOTRAIN_DEPLOY_KEY`; it does not follow the package’s main branch.
To upgrade, commit a new submodule revision here and verify the runtime again.

The image runs package and runtime CPU tests, including exact adapter-weight
comparison between uninterrupted training and optimizer-checkpoint resume using
a tiny Qwen model.
The model deployment workflow publishes the runtime archive by SHA-256 alongside
existing inference bundles. The Nomad host image must match the bundle base ID.

The HTTP server binds to the allocation's loopback port behind the existing
host proxy. Commands have idempotent operation IDs and return bounded event pages.
Workers provide expiring S3 URLs; GPU processes have no Temporal credentials.
Training checks cancellation between microbatches. The workflow renews the exact
allocation's reservation every 30 seconds, including between compute activities.
The host expires it after three minutes without renewal and exits after a short
shutdown grace period. Operation polling does not extend the reservation. A
15-minute bootstrap grace allows the first reservation renewal; model loading
runs as an operation while the server remains available for heartbeats. The host has a
24-hour hard deadline. Manual and scheduled training runs have a 24-hour Temporal
execution timeout, with a separate 12-hour capacity-wait limit per attempt.
Shutdown requests are best effort; recovery never waits for a dead host to
acknowledge. Before replacing an active host, the workflow stops renewals and
waits four minutes, covering an in-flight renewal, lease expiry and exit grace.
Unready hosts have received no training commands. Final shutdown requests do not
block terminal recording on host availability. Training uses the existing fixed
pool; provider provisioning and spot capacity are not part of this executor.

Evaluation uses the task's snapshotted comparison and judge selections. The GPU
runtime generates adapter answers; the worker calls OpenAI, Anthropic or hosted
inference for external models, and uses the reserved runtime when the selected
comparison or judge is the training base itself. Each pair is judged once in a
stable randomized order. Completed pairs are stored in S3 for activity retries.
Legacy all-base evaluations remain supported. Provider errors and truncated
responses fail the run; they are not counted as successful evaluations.

Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and/or `TRAINING_INFERENCE_API_KEY` on the
worker through managed secrets for the corresponding selections. Credentials
never go to GPU hosts. Missing credentials are rejected before building the
dataset or allocating GPUs. GPT-6.1 Sol is the default comparison and judge;
existing task selections are preserved. Published adapters remain unavailable
for promotion until serving qualification is implemented.

Datasets use JSONL with TRL-compatible conversational `prompt` and `completion`
columns. The current recipe accepts text messages and one assistant completion,
masks all prompt tokens and drops overlength examples without truncating targets.
The worker publishes a versioned portable `dataset-manifest.json` with full train/validation/test
artifacts and a separately identified evaluation sample. Runtime and host settings
live in a separate `run-manifest.json`; see the
[run contract](../../../docs/TASK_FINE_TUNING_RUN_CONTRACT.md).
