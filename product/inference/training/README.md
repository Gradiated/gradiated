# Qwen SFT runtime

The initial recipe trains Qwen3-0.6B with rank-two LoRA for fifty steps. The
model revision and recipe are frozen in `packages/contracts/src/training-recipe.json`.
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
15-minute bootstrap grace bounds initial model loading; the host also has a
24-hour hard deadline. Manual and scheduled training runs have a 24-hour Temporal
execution timeout, with a separate 12-hour capacity-wait limit per attempt.
Shutdown requests are best effort; recovery never waits for a dead host to
acknowledge. Before replacing an active host, the workflow stops renewals and
waits four minutes, covering an in-flight renewal, lease expiry and exit grace.
Unready hosts have received no training commands. Final shutdown requests do not
block terminal recording on host availability. Training uses the existing fixed
pool; provider provisioning and spot capacity are not part of this executor.

The initial evaluation uses the same small base model as comparison and judge,
with one judgment per pair, reproducibly randomized answer and generation order,
and group-weighted results. This validates execution;
it is not a production quality benchmark. Published adapters remain unavailable
for promotion until serving qualification is implemented.

Datasets use JSONL with TRL-compatible conversational `prompt` and `completion`
columns. The current recipe accepts text messages and one assistant completion,
masks all prompt tokens and drops overlength examples without truncating targets.
The worker publishes a versioned portable `dataset-manifest.json` with full train/validation/test
artifacts and a separately identified evaluation sample. Runtime and host settings
live in a separate `run-manifest.json`; see the
[run contract](../../../docs/TASK_FINE_TUNING_RUN_CONTRACT.md).
