# Model runtime releases

`model-deployment.yml` publishes the GPU base image to private ECR, verified
runtime archives to private S3, and release records containing their source
revision, base digest, base ID and archive SHA-256. The base contains Ubuntu,
CUDA and basic system dependencies with SSH startup. The verified host bundle
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
Run `python3 tools/gpu/render-config.py`, review the generated manifests and
merge them. Argo owns the deployment. Install the new host release before
selecting model bundles that no longer carry their own `runtime-launch`.

The controller stages new bundles without disturbing active processes. Argo
Rollouts uses one surge replica and zero unavailable replicas. The worker runs
production SDK qualification against the new process incarnation before it is
Ready; the analysis Job checks that qualification before promotion. Keep spare
capacity for the replacement. Previously qualified replicas drain for eleven
minutes before their GPU claims are released.

Base-image updates affect new provider pods only. Update existing host tools over
pinned SSH and verify compatibility rather than resetting a GPU reservation.
See [instance setup](../../docs/INSTANCE_SETUP_PLAN.md) and
[RunPod execution](../virtual-kubelet/README.md) for the supported runtime contract.

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
