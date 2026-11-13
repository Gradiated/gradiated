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

SMG wheels compile in a separate minimal Ubuntu/Python/Rust stage. Only the
pinned toolchain, SMG source, wheel builder and SMG patches feed that stage, so
Depot can reuse the compiled wheel when SGLang dependencies or runtime helpers
change. GLM and DeepSeek share the LoRA variant; Kimi uses the base variant.
Changing any compiler input rebuilds and reruns its native tests. Every bundle
still installs the wheel into its own environment and verifies the complete
packaged runtime. A cold build still pays the compilation cost.

PR checks run CPU-only configuration and verifier regression tests before any
native build. Trigger-only edits to the workflow keep verification scoped to
the changed runtime inputs; edits to jobs, permissions or other workflow content
continue to verify every bundle.

## Host downloads

The root host agent requests short-lived bundle download grants through the
private GPU control listener. The downloader verifies SHA-256 and extracts the
trusted archive into a shared, read-only bundle directory before activation.
No permanent S3 access key is installed on a GPU. Model processes run under a
separate account and receive per-pod scratch space and exclusive GPU UUIDs.

## Deploy a release

Publication does not change production routes. Pin the verified runtime in
`product/inference/gpu/runtimes.json` and select its digest in a pool in
`infra/environments/prod/us-east-1/kubernetes/gpu-inference/models.json`.
[Pools, slots and autoscaling](../virtual-kubelet/README.md#pools-slots-and-autoscaling)
describes that file.

Each release lists a bundle per GPU base in `bundles`, keyed by base ID and
taken from the `release.json` of the runtime job that built it. A host runs the
bundle for its own base, so re-imaging a host onto a new base never strands the
releases it serves. The renderer refuses a base pin in `pins.json` until every
release has a bundle for that base. Keep an older base's bundles until no host
runs that base.
Run `gradctl gpu render-config`, review the generated manifests and
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

## Stage a new pool

A new runtime or GPU type starts as a qualification pool: a fixed replica count
under a private runtime model ID, which passes SDK qualification but is never
routed. The GLM SGLang bundle's source, admission limits, metrics and GPU
qualification are specified in
[the runtime README](../../product/inference/runtimes/glm-sglang/README.md).
Stage an uncensored GLM pool for H200 or B200 from its runtime release record;
the command previews by default:

```sh
gradctl gpu stage-glm-pool --gpu h200 RELEASE_JSON SOURCE_SHA --replicas 1
gradctl gpu stage-glm-pool --gpu h200 RELEASE_JSON SOURCE_SHA --replicas 1 --write
gradctl gpu render-config
```

Review and merge the catalog and manifests through a PR. Test the staged pod
with a normal workspace API key and `x-gradiated-deployment-id` set to its Pod
UID; the response echoes that UID, and a pinned request never falls back.
Normal billing, limits and model access apply.

```sh
curl https://api.gradiated.com/v1/chat/completions \
  -H "Authorization: Bearer ${GRADIATED_API_KEY:?}" \
  -H "x-gradiated-deployment-id: ${POD_UID:?}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"dealignai/glm-5.3-flash-uncensored","stream":true,"messages":[{"role":"user","content":"Compute 13 times 17."}],"max_tokens":256}'
```

Exercise long prompts, mixed traffic, cache accounting, tools, cancellation and
failover through the gateway. Then promote the exact staged pool in a separate
reviewed change, rerunning the command with `--promote --write` and rendering.
Promotion turns the staged count into the pool's `max_replicas` and adds it to
the end of the model's fill order; the model's `min_slots` decides whether it
keeps a floor. Removing the pool, or setting `max_replicas: 0`, withdraws it.
A pool with the same name must be removed before a different release is staged
under it.

## Internal monitoring billing

The production verification workspace uses Gradiated's own prepaid organization.
Continuous probes traverse normal admission and usage settlement; a depleted
prepaid balance makes every deployment fail with HTTP 402. An operator-approved
$10,000 internal reserve credit uses the existing billing ledger without changing
billing mode, charging a payment method or overwriting the operational balance.

Run `gradctl models monitoring-billing` for a read-only production preview.
The separately approved `--apply-credit` operation uses the fixed operator source
ID `gradiated-inference-monitoring-reserve-v1`; retries return the same posting
rather than issuing another credit. The command verifies the fixed production
context, configured workspace, account ID/name/status and prepaid policy. New
reserve grants need a new reviewed source ID and approval; this is not automatic
or recurring funding. Never use this internal reserve for customer accounts.

The gateway applies the immutable credit through its normal ledger replay; do not
write the Valkey balance directly. Verify fresh successes for every deployment
with `gradctl models probe-readiness` afterward.
