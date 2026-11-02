# Model runtime releases

`model-deployment.yml` publishes the GPU base image to private ECR, verified
runtime archives to private S3, and release records containing their source
revision, base digest, base ID and archive SHA-256. The base contains Ubuntu,
CUDA, basic system dependencies and the pinned Tailscale client; it starts no public SSH. The verified host bundle
contains enrollment, downloader, Desmond, runtime launcher and private control
forwarding. See [enrollment ordering](../../product/inference/images/README.md)
before selecting the platform-only base for new provider pods. No image contains
model weights or permanent artifact-reader credentials.

The workflow builds the base first, then verifies each runtime against that exact
base. The runtime archive carries its own Python and pinned dependencies. Build
inputs are hashed; unchanged inputs reuse an immutable release record. Archives
use `bundles/sha256/<digest>.tar.gz` keys and are uploaded before their records.
No mutable latest URL is used for serving.

Builds use Depot and GitHub OIDC. `DEPOT_PROJECT_ID` selects the project/cache;
the AWS deployment role controls ECR and S3 publication. Base or shared packaging
changes verify every runtime, while model-specific changes verify the affected
bundle. Build/import checks do not establish GPU serving correctness.

## Host downloads

The root host agent requests short-lived bundle download grants through the
private GPU control listener. The downloader verifies SHA-256 and extracts the
trusted archive into a shared, read-only bundle directory before activation.
No permanent S3 access key is installed on a GPU. Model processes run under a
separate account and receive per-pod scratch space and exclusive GPU UUIDs.

## Deploy a release

Publication does not change production routes. Pin the verified runtime in
`product/inference/gpu/runtimes.json` and select its digest in
`infra/environments/prod/us-east-1/kubernetes/gpu-inference/models.json`.

Each release lists a bundle per GPU base in `bundles`, keyed by base ID and
taken from the `release.json` of the runtime job that built it. A host runs the
bundle for its own base, so re-imaging a host onto a new base never strands the
releases it serves. The renderer refuses a base pin in `pins.json` until every
release has a bundle for that base. Keep an older base's bundles until no host
runs that base.
Run `python3 tools/gpu/render-config.py`, review the generated manifests and
merge them. Argo owns the deployment. Install the new host release before
selecting model bundles that no longer carry their own `runtime-launch`.

The controller stages new bundles without disturbing active processes. Argo
Rollouts uses one surge replica and zero unavailable replicas. The worker runs
production SDK qualification against the new process incarnation before it is
Ready; the analysis Job checks that qualification before promotion. Model-specific
surge and unavailable settings control replacement on packed fleets. Existing
allocations retain their admitted RAM requests when the catalogue changes its
scheduling request; new allocations must match the new request, and all
allocations must still match the pinned CPU, GPU and memory limits. Install a
host bundle supporting admitted-request preservation before changing an active
release's RAM request. Previously qualified replicas drain for eleven
minutes before their GPU claims are released.

Base-image updates affect new provider pods only. Update existing host tools over
Tailscale SSH and verify compatibility rather than resetting a GPU reservation.
See [instance setup](../../docs/INSTANCE_SETUP_PLAN.md) and
[RunPod execution](../virtual-kubelet/README.md) for the supported runtime contract.

## GLM SGLang canary

The `glm-5-3-flash-sglang` bundle is a separate, pinned PCP2 runtime. Publishing
it does not replace `glm-dealign` or send production traffic to SGLang. Its
source, native admission limits, metrics and required GPU qualification are
specified in [the runtime README](../../product/inference/runtimes/glm-sglang/README.md).

After the source PR passes checks and review, deploy and verify the updated worker
and gateway before staging the model. The normal model workflow publishes the
immutable runtime release record. Stage that record with the qualified source
revision; the command previews changes by default:

```sh
node tools/models/stage-glm-sglang-canary.mjs RELEASE_JSON QUALIFIED_SOURCE_SHA
node tools/models/stage-glm-sglang-canary.mjs RELEASE_JSON QUALIFIED_SOURCE_SHA --write
python3 tools/gpu/render-config.py
node tools/models/model-replica-rules.mjs
```

Review and merge the generated catalog and manifests through a PR. The initial
`glm-dealign-sglang` Rollout has one replica, two GPUs, no surge, a fixed maximum
of one replica, and placement on the existing two-B300 host. The ten-replica vLLM
primary remains unchanged. **The first deployment is isolated from ordinary
production requests**, including after warmup and SDK qualification succeed.

Its immutable runtime uses a private model identity that is not registered in
the public catalog. The reserved `serving-model-id` annotation maps it to the
uncensored public model for the new worker, while `serving-mode: qualification`
keeps its deployment row unavailable for normal routing. An older worker ignores
the mapping and cannot publish the private identity into the uncensored pool.
The private runtime identity remains unchanged when promoting the canary.

Test it with a normal workspace API key and
`x-gradiated-deployment-id` containing the canary Pod UID. The response must echo
that UID; a targeted request does not fall back to the production pool. Normal
billing, limits and model access apply, and draining targets are rejected.
Automated SDK checks use the same header with their own short-lived key in the
configured verification workspace, which identifies verification traffic.

```sh
curl https://api.gradiated.com/v1/chat/completions \
  -H "Authorization: Bearer ${GRADIATED_API_KEY:?}" \
  -H "x-gradiated-deployment-id: ${CANARY_POD_UID:?}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"dealignai/glm-5.3-flash-uncensored","stream":true,"messages":[{"role":"user","content":"Compute 13 times 17."}],"max_tokens":256}'
```

Exercise cold 500K/1M prompts, mixed short/long traffic, cache accounting, tools,
cancellation, bounded queuing and failover through the gateway before promotion.
Then stage a **separate reviewed promotion**:

```sh
node tools/models/stage-glm-sglang-canary.mjs RELEASE_JSON QUALIFIED_SOURCE_SHA --promote --write
python3 tools/gpu/render-config.py
node tools/models/model-replica-rules.mjs
```

Promotion requires the exact previously staged isolated canary and immutable
runtime. It changes `serving_mode` to `production`; it does not increase replicas
or replace the primary. The Pod template change can replace the one canary, which
must qualify again before serving. Its update pauses after SDK analysis. Argo
skips step execution on initial creation; isolation and the replica/GPU/placement
bounds enforce the initial test stage. Argo weights apply within this Rollout,
not between the vLLM and SGLang pools.

Qualification-only replicas contribute zero to production desired and minimum
counts. After promotion, the optional canary contributes one desired and zero
minimum replicas. The minimum aggregates both Rollouts: nine primary replicas
plus one production canary satisfies the floor of ten. A missing production
canary triggers the existing twenty-minute scale-up-stalled warning. Check each
Rollout during the soak; the aggregate floor does not assert ten healthy vLLM
replicas.

Keep the production canary for at least thirty minutes after successful SDK and
real-gateway checks. Inspect errors, cancellations, cache accounting, TTFT tails,
per-stream decode speed and native queue depth. Increase by one two-GPU instance
per reviewed stage, qualify and soak before removing corresponding vLLM capacity.
Do not infer capacity from a finite burst or expand automatically after the first
canary. Preserve the existing vLLM release for rollback.

To withdraw the canary, set its `autoscaling.paused_replicas` to `0`, render, and
merge that change. Keep the primary unchanged. Removing the Argo application alone
does not stop retained resources. The staging command refuses to overwrite an
existing canary, private runtime definition or intentional rollback silently.

## Internal monitoring billing

The production verification workspace uses Gradiated's own prepaid organization.
Continuous probes traverse normal admission and usage settlement; a depleted
prepaid balance makes every deployment fail with HTTP 402. An operator-approved
$10,000 internal reserve credit uses the existing billing ledger without changing
billing mode, charging a payment method or overwriting the operational balance.

Run `node tools/models/monitoring-billing.mjs` for a read-only production preview.
The separately approved `--apply-credit` operation uses the fixed operator source
ID `gradiated-inference-monitoring-reserve-v1`; retries return the same posting
rather than issuing another credit. The command verifies the fixed production
context, configured workspace, account ID/name/status and prepaid policy. New
reserve grants need a new reviewed source ID and approval; this is not automatic
or recurring funding. Never use this internal reserve for customer accounts.

The gateway applies the immutable credit through its normal ledger replay; do not
write the Valkey balance directly. Verify fresh successes for every deployment
with `node tools/deployment/inference-probe-readiness.mjs` afterward.
