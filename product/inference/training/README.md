# Training runtime

Training recipes are selected from the canonical model catalog and frozen per run.
Qwen3 supports 0.6B, 1.7B, 4B, 8B, 14B and 32B bases on one GPU. GLM-5.3-Flash
uses the pinned BF16 checkpoint on four GPUs, eager attention and activation
checkpointing. Both use rank-two LoRA with a fifty-step qualification cap. Future runs validate
every five steps, stop after three checks without an absolute loss improvement
greater than 0.0001 (minimum ten steps), and publish the lowest-validation-loss
adapter. The recipe uses seeded epoch shuffling, five warmup steps and cosine
learning-rate decay through Transformers. Validation loss is weighted by completion
tokens on a fixed seeded sample of up to 256 examples; the test split remains
reserved for final evaluation. These are configurable starting defaults, not tuned
hyperparameters or a general production training budget. The GLM path has a tiny
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
locked by this runtime. CI fetches that exact commit with a read-only token from the
Gradiated Autotrain Reader GitHub App (`AUTOTRAIN_APP_CLIENT_ID`,
`AUTOTRAIN_APP_PRIVATE_KEY`); it does not follow the package’s main branch.
To upgrade, commit a new submodule revision here and verify the runtime again.

The image runs package and runtime CPU tests, including exact adapter-weight
comparison between uninterrupted training and optimizer-checkpoint resume using
a tiny Qwen model. Checkpoints also preserve the best adapter, early-stopping
state and learning-rate scheduler; a resumed run cannot reset its patience.
Existing frozen run manifests and runtime bundles retain their original behavior.
The model deployment workflow publishes the runtime archive by SHA-256 alongside
existing inference bundles. The Nomad host image must match the bundle base ID.

The HTTP server binds to the allocation's loopback port behind the existing
host proxy. Commands have idempotent operation IDs and return bounded event pages.
Workers provide expiring S3 URLs; GPU processes have no Temporal credentials.
Artifact downloads and uploads retry transient DNS, connection, timeout and HTTP
service failures at most three times within a shared ten-minute deadline. Downloads
restart from zero and retain the final checksum check; uploads retry the same
bytes to the same signed object key. Authentication, certificate and integrity
failures are not retried. Retry logs contain bounded reasons without URLs. Failed
operation events retain exception/cause types and HTTP status for diagnosis after
the allocation is cleaned up.
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

Evaluation token-cost estimates use hosted catalog prices for the training base
and `GET /api/v1/models?external=true` for external comparisons. The API owns the
OpenRouter loader and its five-minute process-memory cache; plain `/models` only
reads the hosted catalog. Each evaluation saves its price snapshot in S3 at
`runs/{run_id}/evaluation/pricing.json`, so retries use the same rates. Input,
output (including reasoning), cache reads/writes and long-context price tiers
are counted from generation usage. The estimates exclude GPU and judge costs
and do not affect billing. The console reads the saved evaluation summary;
the proxy and collector do not load this catalog. Missing rates or token usage
leave cost unavailable without failing evaluation; legacy results are not
backfilled. The existing Qwen-only placeholder estimate remains supported.

Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and/or `TRAINING_INFERENCE_API_KEY` on the
worker through managed secrets for the corresponding selections. Credentials
never go to GPU hosts. Missing credentials are rejected before building the
dataset or allocating GPUs. GPT-6.1 Sol is the default comparison and judge;
existing task selections are preserved. A successfully verified run publishes an
available task version with its immutable adapter checksum and training base
revision. Users can promote that version; inference requires a compatible host
with LoRA enabled. Hosts download adapters on demand, while vLLM owns the CPU and
GPU adapter caches.

When the base model also judges its own comparisons, judgments have a bounded
256-token output budget so reasoning models can finish. Only the final answer
after a completed thinking segment is interpreted as A, B or TIE; unfinished or
unrecognized judgments remain unresolved.

Datasets use JSONL with TRL-compatible conversational `prompt` and `completion`
columns. The current recipe accepts text messages and one assistant completion,
masks all prompt tokens and drops overlength examples without truncating targets.
The worker publishes a versioned portable `dataset-manifest.json` with full train/validation/test
artifacts and a separately identified evaluation sample. Runtime and host settings
live in a separate `run-manifest.json`; see the
[run contract](../../../docs/TASK_FINE_TUNING_RUN_CONTRACT.md).
