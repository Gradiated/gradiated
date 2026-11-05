# Kubernetes workers on RunPod

RunPod gives us a container with attached GPUs, rather than a machine where we
can install a normal kubelet and container runtime. The GPU controller runs in
EKS and uses Virtual Kubelet to represent each enrolled RunPod host as a
Kubernetes Node. Kubernetes schedules model pods and training Jobs onto those
Nodes; a small host agent starts their pinned runtime bundles.

The adapter supports our trusted model and training runtimes. It does not run
arbitrary container images, provide pod IPs or CNI networking, mount Kubernetes
volumes, or expose kubelet logs and exec. Bare-metal hosts should use an ordinary
kubelet and container runtime instead.

## Scheduling and execution

`cmd/gpu-controller` watches the `gpu-inference` namespace. Three controller
replicas run on separate EKS nodes and elect one leader. After election, the controller reads each host's durable generation, verifies
that it still owns the Kubernetes Lease, then claims the next generation with a
unique term. Operations require both values. Claim retries reuse the same term;
a replaced leader cannot mutate workloads, even if its numeric generation is
reused after state restoration. Recreating the Kubernetes Lease does not reset
host generations. Existing reservations adopt this protocol on their first claim.
A host answers a request with a stale generation or term with 409
`stale_epoch`. If the host's generation is now below the one the leader holds,
as after a re-image, the leader claims it again under its lease and retries
once. A host at or ahead of that generation belongs to another leader and is
never claimed back; a controller that has lost the Lease never claims.

Each RunPod host advertises its GPU count, CPU budget, memory budget and GPU
model. Kubernetes places a pod using those resources and its node selector.
The host agent assigns physical GPU UUIDs, takes exclusive GPU locks, and puts
the pod's processes in a cgroup with CPU, memory and process limits. It refuses
a GPU that already has a compute process. Tensor-parallel and single-GPU
workloads can share a host without sharing a GPU claim.

`product/inference/gpu/runtimes.json` pins the supported bundles and their execution settings. The
agent accepts one runtime container per pod and rejects commands, environment
overrides, mounts and host networking. Models run as `runtime`; their Desmond
reporter runs as `desmond`. The management agent runs as root.

Inference processes restart with bounded backoff. Training uses Kubernetes Jobs
with `restartPolicy: Never` and no automatic retry, so a failed trainer cannot
silently repeat work. The Temporal workflow owns training attempts, reservation
renewal and cleanup.

## Private traffic and credentials

The controller calls the host agent through the host's existing private
`gpu-<instance UUID>` Tailscale Service. A host-specific management key protects
these operations from model processes on the same GPU host. This key is not
inference authentication.

The host proxy exposes `/alloc/<Pod UID>` over Tailscale. The product worker
registers that URL in the existing deployment inventory, so the gateway keeps
using the same routing, streaming and KV-cache machinery.

Desmond reports through the loopback Tailscale bridge on port 3004. Training
receives short-lived S3 download and upload grants for its artifacts. Kubernetes
credentials, AWS administrative credentials and database credentials stay in
EKS. GPU hosts have no VPC route or Tailscale grant to PostgreSQL, Valkey or the
Kubernetes API.

## Qualification, updates and deletion

A model process being healthy sets `RuntimeReady`; it does not make the pod
ready for serving. An EKS worker makes a targeted request through the production
SDK and records the pod UID and process incarnation that passed. A process
restart requires another verification. The deployment inventory keeps
unqualified pods unavailable to normal customer requests.

Argo Rollouts owns model updates. It permits one surge replica and zero
unavailable replicas, and its analysis job checks the latest pods' SDK
qualification. Keep enough spare GPU capacity to start the replacement while
the old replica remains available. The verifier runs on an EKS CPU node and
needs only permission to read GPU pod status.

Deleting a previously qualified inference pod rejects new allocation requests
and gracefully reloads the host proxy. Once the old proxy workers finish their
accepted requests, it stops the model processes; eleven minutes is the maximum
drain, rather than a fixed sleep. Queued requests, uploads and response streams
keep those workers alive. Because the proxy is shared, an older stream to another
allocation can also delay release. Missing proxy acknowledgement or unreadable
worker state retains the remaining timeout, including after an agent restart.
Cleanup verifies that its cgroup is empty before releasing GPU claims. Unqualified canaries and
training pods stop without that inference drain. Kubernetes pod deletion is
completed after host cleanup; it does not add another grace period. Failed
cleanup retains the claim. Training data and per-pod LoRA caches are removed
after processes stop; diagnostic logs remain on the host. Process birth times
prevent signalling a reused PID.

Controller, agent and proxy restarts retain model processes. A host reset loses
node-local state and requires enrollment again; it must not be used as a
migration or recovery step on a retained reservation.

## Enrollment and checks

Enrollment (`gradiated-host enroll`, see
[`product/inference/host`](../../product/inference/host)) installs the pinned host
bundle and the root-only configuration; the host agent then stages the runtime
bundles the controller asks for. Add the host as a `GpuHost` in
`infra/environments/prod/us-east-1/kubernetes/gpu-inference/hosts.yaml` and run
`python3 tools/gpu/render-config.py` (requires PyYAML 6.0.2). This generates the
host key projection and named Node/Lease RBAC. The inventory stores secret
references, never key values.

The controller reads its hosts only from the `GpuHost` objects, when it becomes
leader; an invalid object is skipped and the operator marks it Degraded. If the
objects cannot be listed, the leader gives up the lease so another replica tries.
When any `GpuHost` changes (added, removed or edited), the leader steps down and
the next leader restarts every host's virtual node, not just the changed one.
Heartbeats pause for about a minute; serving processes on the hosts keep running,
as they did when a host list change restarted the controller. Each node
carries `gradiated.com/fault-domain`, the host's RunPod machine ID, for
topology spread and anti-affinity. The `gpu-fleet` operator
(`product/services/gpu-fleet`) keeps each host's private Service, reports its
health in its `GpuHost` status, and holds a deleted `GpuHost` until no pods run on
it; see the retirement steps in the [instance setup plan](../../docs/INSTANCE_SETUP_PLAN.md).

All production serving replicas and training Jobs use Kubernetes. Existing
RunPod containers retain a suspended legacy main process only to preserve their
reservation; it has no jobs or cluster access. New hosts use the GPU base image.

Use Go 1.26.10, matching the compiler pinned in CI and the controller builder
image. Run the local adapter checks with:

```sh
cd tools/virtual-kubelet
go test -race ./...
go vet ./...
python3 host_agent_test.py
python3 -m unittest discover -s ../../product/inference/host/tests -p 'test_*.py'
```

CI also runs the pinned Go vulnerability checker against the controller's
source call graph and fails on reachable known vulnerabilities. For the same
local check, run `go run golang.org/x/vuln/cmd/govulncheck@v1.9.0 ./...` from
this directory. Keep the compiler, builder digest and CI pin aligned when
applying Go security updates.

Enrollment reads a typed JSON payload on stdin: instance UUID, host-management
key, one-time GPU-tagged Tailscale auth key, private API tailnet address and the
pinned host bundle. The host receives no OAuth, Kubernetes, database or AWS
access credential. Bundle downloads use temporary grants from the private
control bridge.

Model catalogue changes are rendered into the controller ConfigMap by
`python3 tools/gpu/render-config.py`. The controller asks each host to stage the
pinned bundles through private download grants. Downloads run outside the host
operation lock; activation and pod creation share a lock. Active runtime profiles
remain unchanged until their pods drain. Select the runtime and placement in `gpu-inference/models.json` alongside the
catalogue; an unstaged candidate retries while existing replicas keep serving.
The controller image is built and pinned by the normal application release.

The host agent accepts `GLM_SGLANG_PROFILE` values `b300-pcp2`, `b200-pcp2`, and
`h200-tp2` from the runtime catalogue. It validates these profiles when rebuilding
the proxy for existing pods as well as before launching new ones, so a bundle
update must support every active runtime's environment. Configuration tests check
the current catalogue against the host agent; an incompatible agent can crash
at startup and trigger the launcher's bundle rollback without restarting models.

The model configuration names the runtime digest, replica count, deadline and
placement. Optional `max_surge` is a positive integer, defaulting to one; GLM
Dealign permits two extra replicas while retaining `maxUnavailable: 0`. Actual
parallel startup depends on spare GPU, CPU and memory capacity. The current
fleet fits only one extra full-size GLM replica; a second candidate can remain
Pending until capacity is released. This ceiling does not provision capacity or
guarantee two simultaneous starts. The renderer supplies the common canary strategy, qualification,
service account, drain period and resources from the runtime catalogue.
Rollouts have no manual pause: the default canary moves to half weight, runs
SDK analysis and then completes. `rolling_update: true` moves directly to the
target revision without that half-weight canary. Per-pod SDK qualification still gates
readiness, and the rollout retains its final SDK analysis. The H200 FP8 rollout
uses this mode with five replicas, `max_surge: 0` and `max_unavailable: 1`, so
it replaces one replica at a time while keeping four available. Other models
retain the existing canary strategy by default. Do not
edit generated Rollouts directly. Non-inventory fields in controller and RBAC
manifests remain editable; rendering preserves them. CI checks that generated
fields match the inputs. Remove a retired host Service or model Rollout explicitly after draining
its workloads; rendering and --check fail if retired resources remain.

## Argo CD applications

Each model is its own Argo CD application, so one model's sync, health or
pruning never waits on another. `render-config.py` writes each model's Rollout
and ScaledObject to `gpu-inference/models/<model>/`, and the `gpu-models`
ApplicationSet (`platform/gpu-models.yaml`) creates a `gpu-model-<model>`
application for every such directory from one template; adding a model is a
new directory. Two plain applications read the rest of `gpu-inference/`:
`gpu-fleet` (the `GpuHost` CRD and objects, the operator and its pins) and
`gpu-platform` (everything else: the namespace, gpu-controller, credentials,
RBAC, the training priority class and qualification). `gpu-fleet` creates the
namespaces it deploys into, but the operator can cordon nodes only once
`gpu-platform`'s `rbac.yaml` has synced.

Removing a model is explicit, because deleting its directory deletes its
application but leaves the Rollout serving (`preserveResourcesOnDeletion`):

1. Withdraw the model from traffic.
2. Remove it from `models.json` and delete `gpu-inference/models/<model>/` in
   the same change, render and merge.
3. Wait until Argo has deleted the `gpu-model-<model>` application; its Rollout
   and ScaledObject keep running, no longer managed. Deleting them earlier
   would let the application's self-heal recreate them.
4. Run `kubectl -n gpu-inference delete rollout,scaledobject <model>`. Its pods
   stop with their normal termination grace period.

## Model autoscaling

KEDA owns each Rollout's replica count through the standard Kubernetes scale
API. Argo CD ignores `spec.replicas` while autoscaling is active. With an explicit
`paused_replicas` override, Git owns the paused replica count so a concurrent
sync cannot restore the bootstrap count after KEDA pauses. Argo still reconciles model releases,
placement and scaling policy. Set the minimum with `replicas` and the ceiling
and initial target in `models.json`'s `autoscaling` field, then render the
manifests. Desmond continues reporting short-lived health directly to the
private control API for routing; Prometheus supplies scaling measurements.

Three gateway signals inform the HPA: concurrent generations over the last
minute, runtime seconds per second over two minutes (so short requests between
scrapes count once a rate baseline exists), and capacity rejections. Each signal is scoped to the exact
model and summed across gateway replicas. The HPA takes the largest recommendation.
Capacity rejections request the configured ceiling; customer balance and
concurrency policy rejections do not. The initial concurrency targets are 0.7
for Kev's single execution slot and 16 for the batched runtimes. The batched
targets are conservative starting policy, not measured throughput guarantees;
tune them against time to first token and queue pressure under representative
traffic. GPU memory allocation alone is not a useful scale-down signal.
Prometheus samples traffic; a first successful burst that finishes before the
first scrape can be missed. Runtime work series are created at admission and
for every fallback candidate before dispatch so a scrape during an in-flight
request establishes zero.
Sustained traffic supplies the subsequent samples. The capacity timestamp
signal captures a first rejection even without a preceding scrape. Warm minimum
replicas remain necessary for sudden bursts; autoscaling cannot load a model
in time for a burst that has already finished.

All queries require fresh, complete gateway telemetry. Missing samples or a
Prometheus outage trigger a fallback that retains the current replica count
when it exceeds the minimum. Scale-up adds at most one replica per minute;
scale-down waits ten minutes and removes at most one per 750 seconds, longer
than the runtime drain. New replicas become available only after the existing
SDK qualification. None of this provisions or resets a provider GPU.

The current ceilings are Kev 2, GLM 2 and DeepSeek 2. Kev retains its third RTX
host for a zero-unavailable rollout. GLM retains a third B300 host for its hard
host anti-affinity during a rollout. DeepSeek can grow from one to two replicas.
These bounds preserve existing availability and rollout capacity; raising them
requires reviewing GPU, CPU, memory, placement and concurrent training demand.
Training Jobs use the `gpu-training` PriorityClass, below the default priority of
model pods, so a model replica or rollout pod that cannot fit preempts training
rather than waiting. Training never preempts. A preempted trainer resumes in a new
Job from its latest checkpoint, with up to three attempts per training stage.

DeepSeek selects eight-GPU hosts: the current four-GPU training host does not have
space for its weights alongside the existing training cache. Node labels publish
the host GPU count, and Kubernetes enforces this placement selector. At two
DeepSeek replicas, each eight-GPU host also runs GLM, leaving no contiguous
four-GPU slot for a DeepSeek rollout surge. Scale DeepSeek to its minimum before
updating its runtime, or provide another eligible host; do not assume spare GPUs
split across hosts satisfy a tensor-parallel replica.
Scaling down a model releases GPUs but does not reduce the RunPod reservation bill.

Availability alerts use the Git minimum, so normal scale-up warmup does not page.
No ready replicas still alerts after fifteen seconds, and falling below the
minimum alerts after thirty seconds. Additional requested capacity that remains
unready for twenty minutes has a separate warning. Keep the minimum large enough
for immediate traffic; autoscaling adds capacity after model startup.

## Rollout alerts

`GpuRolloutFailed` warns when Argo Rollouts reports a Rollout as `Abort`,
`Timeout`, `Error` or `InvalidSpec`: it aborted at its progress deadline, failed
SDK qualification, or cannot reconcile. It does not retry automatically. Free
capacity if needed, then run `kubectl argo rollouts retry rollout <name> -n
gpu-inference` or push a fix. `GpuRolloutBlocked` warns when a model pod has had no
GPU host for 15 minutes, before the deadline aborts the rollout. To free capacity,
lower another model's `replicas` or `max_replicas` in `models.json`, or pin it
temporarily with the ScaledObject's `autoscaling.keda.sh/paused-replicas`
annotation and remove the annotation afterwards.

## Recovery and disk limits

Host ownership records are written through a shared helper that fsyncs file data
before replacement and the parent directory before acknowledging success.
Process handles include boot and PID namespace identities as well as PID birth
times. Serving task recovery retains the pod UID and requires SDK qualification
of the new process incarnation. Training tasks that already started never retry
automatically. Unknown processes retain their GPU claims instead of allowing
another task to start. The private proxy reconstructs routes from durable pod state
and reloads when they differ, retaining existing connections. Its 660-second
read timeout covers the production generation budget, including non-streaming
requests that send no response bytes until completion. Child tasks are reaped; their cached process objects are
not durable workload state.

Every minute, cleanup preserves configured, active and staging bundles. It keeps
two verified unused bundles and at most twenty retired pod diagnostic directories
for up to seven days. Live processes or occupied cgroups prevent retirement; an
unrecorded live process blocks bundle cleanup. Model weights use each host's configured `hf_home`; runtime profiles must not override it with a second cache location. Before a pod starts, the agent sizes its pinned weights (the release model plus a distinct pinned tokenizer repository, which for Kev is the base checkpoint it loads) from the Hugging Face
file listing and evicts whole `models--*` repositories from that cache, least
recently used first, until the missing files (blobs another revision already cached count as present), the unused part of each LoRA
pod's `LORA_DISK_CACHE_BYTES` budget and `model_cache_reserve_gib` (default 64)
fit. Models used by any pod on the host are never evicted, even at an unpinned revision; if any pod state on the host cannot be read, eviction is skipped. Unfinished
downloads of models in use keep their space. Runtimes still download the files
themselves. If sizing fails or space cannot be freed, the pod starts anyway and
`runtime.log` records why.
Diagnostic logs are bounded at 32 MiB per file using copy/truncate of the recent
16 MiB, retaining the writer's inode. Concurrent log lines can be lost during
truncation; inference output and durable training artifacts use separate paths.

CI runs Go race/vet checks, a real Go-to-Python HTTP fencing test, host recovery
and cleanup tests, injected storage failures, process crashes around file
replacement, bootstrap checks and downloader checks. These simulate process and
storage failures without releasing GPU reservations. Physical host loss still
requires replacement capacity; a provider reset requires deliberate enrollment.

## Host software bundles

Model deployment publishes a `host` bundle alongside runtime bundles. Its
`host-runtime-release` artifact contains `release.json` with the archive digest
and base compatibility ID. After successful publication from main, the release
GitHub App commits the compatible host bundle pin and its generated copies to
main, as it does for application image versions. Argo CD syncs the pin and the
fleet operator updates hosts in place. No second pull request is needed.
Manual host pins, including rollbacks, persist across unrelated model releases
until shipped host software changes or an explicit pin change supersedes them.
Verification-only changes, release tooling, documentation, unrelated image-catalog
edits and base-image-only changes do not lift that hold. An archive discarded
during the manual override remains held even if its build inputs change; select
it explicitly to restore it. A new host fix must produce a different archive.
Promotion rejects stale host build inputs and incompatible base IDs, retries
concurrent Git pushes by regenerating on current main, and preserves the provider
image and its digest. Release cache keys and stale-build checks include the model
deployment workflow and shared build configuration, so packaging changes rebuild
and verify the artifact. Verification-only workflow changes still retain manual
rollback pins. A base image migration still needs an explicit pin change.
Host bundles contain the agent, enrollment and state
helpers, Desmond, runtime launcher and downloader. The base contains platform
dependencies, the pinned Tailscale binaries and `gradiated-host`, which runs
Tailscale, the private control bridge and the launcher; it has no SSH server.
Enrollment installs a verified seed and retains a recovery copy on disk. Later
host releases update the active version without rebuilding the base or model
bundles. Historical recovery fixtures under `images/gpu-base/recovery/` qualify
legacy hosts only. See [the GPU images guide](../../product/inference/images/README.md).

`gpu-inference/pins.json` is the only place the host image and bundle are pinned:
the GPU base `image` (its input-hash tag, because RunPod pulls ECR images only by
tag), the `imageDigest` that tag must resolve to, and the `hostBundle` (`sha256`
and `baseId`). The renderer writes the image into
`infra/environments/prod/runpod/templates.json` and the image and bundle into the
ops-mcp workload, and `--check` fails if either copy differs. On a pull request
that changes the pins, `.github/workflows/gpu-pins.yml` checks in ECR that the
tag resolves to `imageDigest` and that the image's `/etc/gradiated/base-id`
equals `hostBundle.baseId` (`tools/gpu/check_pinned_image.py`). ECR tags in this
account are immutable, so the operator, which sees only the tag RunPod reports,
compares tags. Switching the operator to `MODE=act` needs a v3 image and a v3
bundle pinned together. Pin a published host release and commit the generated
configuration:

```sh
python3 tools/gpu/pin-host.py /path/to/host-runtime-release/release.json
python3 tools/gpu/render-config.py --check
```

A host whose bundle base differs from its own rejects it before download. Hosts use the existing downloader and short-lived control-bridge grants. Root
copies the downloaded archive into private storage and independently verifies its
digest before extracting; it then checks the file manifest and copies the result into root-owned `/var/lib/gradiated-kubelet/host/<digest>`. Downloaders
cannot modify the promoted code or launcher state. Extraction, validation and
atomic promotion use one root-owned tree. Safe, hashed top-level helpers can be
added without updating the immutable launcher; archive size and file count are
bounded. Agent processes and their children disable Python bytecode writes so
imports cannot add files to the immutable bundle or invalidate rollback checks.
The launcher consumes fenced `pending`
requests and keeps current, previous, trial and failure in one atomic
`status.json` record; symlinks are only read during migration from the earlier
layout. It commits an update before running it and consumes the previous target
on rollback, so a failing recovery target falls back to the base. It requires a
loopback ping from the new digest within 120 seconds and rolls back after three
agent exits within ten minutes. A failed digest is not retried automatically.
An interrupted trial or an unclean launcher exit consumes the previous target
on restart. Normal launcher shutdown clears its running marker; storage failure
keeps that marker conservative, so a rejected agent cannot resume unnoticed. Storage errors preserve the running
agent or start the on-disk recovery agent; new updates wait until state can be
committed. The agent exits if its launcher dies, while independent model workers
keep running. Current,
previous, one unused verified bundle, and code referenced by live task/proxy
workers are retained. This last exception preserves workers across successive
agent updates.

### Rolling hosts onto the pins

The `gpu-fleet` operator (`product/services/gpu-fleet`) moves hosts onto the pins
one at a time, and records each host's progress in `status.rollout` of its
`GpuHost`, so a new leader or a restarted operator resumes at the same step:

- A host on another image is re-imaged: cordon its node (or block, if it runs a
  training pod); for each model with
  pods on it, raise the model's replica count by pausing its KEDA ScaledObject
  (`autoscaling.keda.sh/paused-replicas`) and wait until the replacements are
  Ready on other hosts; mark the host's pods to be removed first
  (`controller.kubernetes.io/pod-deletion-cost`) and lower the count again, so no
  model ever has fewer Ready replicas than it had; resume KEDA; re-image the pod
  through RunPod with a single-use bootstrap key; wait for
  `gpu-bootstrap-<pod>`; free the `gpu-<instance id>` name; run
  `gradiated-host enroll`; wait for promotion and claim the exact name; wait until
  the host answers on the pinned bundle with its node Ready; soak five minutes;
  uncordon. Every step has a deadline. The operator records the surge and the
  re-image request (with the key's ID) before acting, so a restart at any step
  neither surges twice nor re-images twice, and it revokes every key it minted
  (failures increment `gradiated_gpu_fleet_key_revocation_failures_total`).
  RunPod shows the new image as soon as it accepts a re-image, and the container
  starts once the image is pulled; the operator waits for that, and asks again
  only if the pod is still on its old image ten minutes later. If RunPod refuses
  the request (a 4xx answer), the key is revoked and the request sent again at
  once; after a timeout or a 5xx, the request and key stand, because RunPod may
  have applied it. If there is no room for a replacement, the operator reverts
  the surge, uncordons the host and marks it Blocked; no other host starts a
  re-image until the blocked host's serving pods would fit on the other Ready,
  schedulable hosts with the same GPU product, and each retry of the same host
  waits twice as long as the last (5 minutes, then 10, up to an hour), so
  autoscaling that only fills GPUs never restarts it. `GpuHostRolloutBlocked`
  fires after two hours blocked.
- A host on the pinned image but another bundle is updated in place: once every
  serving pod on it is Ready, the operator records them and writes the bundle to `status.rollout.bundle`, the controller (which holds the
  fencing epoch) sends it with `configure`, and the operator requires the host to
  run it for five minutes with every serving pod still on the host, Ready, with
  its qualified runtime unchanged.
- A host that has never answered since its `GpuHost` was added, and whose tailnet
  device has not been seen since then, is enrolled after ten minutes. A host
  whose container was wiped is re-enrolled when all of these hold: its agent
  times out (an operator-side error, such as a missing key, an unreadable
  answer, or an egress Service with no DNS name or nothing listening, proves
  nothing); no tailnet device for it is connected; its container
  started at or after the agent last answered and after the device was last
  seen; and ten minutes have passed since that start. A host that is merely
  unreachable, as in a provider network outage, keeps its device seen after its
  container started and is left alone. The operator checks again that the host
  is silent and disconnected immediately before it re-images it through RunPod.
  Recovering and enrolling hosts go ahead even while a re-image is blocked.

Hosts with no serving pods go first, so the spare host proves a new image before
any other. The first failure holds the fleet: the host stays cordoned, its
`GpuHost` is Degraded with the step and reason, `GpuHostUpdateFailed` fires, and
no other host starts until the pins change or someone sets the
`fleet.gradiated.com/retry` annotation on the host to a new value; a retry
restarts only that host. A host on the old image keeps its old bundle until it
is re-imaged.

Before an in-place bundle update, every Ready model pod must have a qualified
runtime and enters the protected baseline for verification and soak. Non-Ready
pods whose current containers failed SDK qualification do not block the update.
Neither do non-Ready pods whose models are explicitly `unavailable` in the live
PostgreSQL catalog: the worker intentionally skips SDK qualification for those
models, and the gateway rejects their customer requests. The operator resolves
catalog identity from `gradiated.com/serving-model-id`, falling back to
`gradiated.com/model-id`; the Rollout's name is not the catalog identity.

Enabled models still wait for readiness and qualification. Missing identities,
unknown models and retired models retain the default wait; a catalog read error
leaves `Apply` unchanged and is retried. After reading the catalog, the operator
reads pods again so a newly Ready pod joins the baseline. Every Ready pod stays
protected regardless of model availability or qualification-error annotations.
Serial host order, failure holds and image rollout behavior are unchanged. This
allows host maintenance while a model is disabled without changing its catalog
status, fabricating a qualification result, or restarting model processes.
Existing installations must reapply the reviewed
[`gpu-fleet-db-bootstrap.yaml`](../../infra/environments/prod/us-east-1/kubernetes/operations/gpu-fleet-db-bootstrap.yaml)
job before deploying this catalog-aware gate, to grant the fleet role read access
to `models`. Confirm the grants and remove the temporary bootstrap resources as
described in the operations guide. The operator reuses its rotating PostgreSQL
credential and needs no additional Kubernetes or AWS permissions.

Only the leader acts, and it checks its lease before every side effect. Status
writes carry the `GpuHost`'s resourceVersion, so a deposed leader's write fails.
An enrollment records who started it and when; a new leader waits until that run
could no longer be going before it starts another. Admission policies in
`gpu-fleet.yaml` let the operator's service account change only a pod's
`controller.kubernetes.io/pod-deletion-cost` annotation, a node's
`spec.unschedulable` and its `fleet.gradiated.com/cordoned-by` marker, and a
ScaledObject's `autoscaling.keda.sh/paused-replicas` annotation. A rollout marks
its cordon `gpu-fleet-rollout` (the drain uses `gpu-fleet`) and uncordons only a
node it marked, so a node someone cordoned by hand stays cordoned.

The operator runs in `MODE=observe` until switched to `act`. Observe mode holds
only the destructive steps: re-image, enroll and recover are written to each
`GpuHost`'s `status.plan` as what the operator would do, and a rollout already
under way pauses. In-place bundle updates keep running in both modes, because
the host's launcher rolls a failed bundle back by itself. The operator reads each
pod's image and container start from RunPod, with the key in
`gradiated/prod/platform/gpu-fleet` (property `runpod-api-key`); it tries to read
that key on every pass until it can, and again after RunPod rejects it, so a
rotated key needs no restart. Until it has a key it reports re-imaging hosts as
waiting.
Until PR 4 removes it, ops-mcp keeps its own enrollment path for hosts it
registers.

The operator exports host bundle versions, drift from the pin, rollout steps and
failures under the metric names the controller used before
(`gradiated_gpu_host_*`), so the controllers dashboard and alerts are unchanged;
`GpuHostRolloutStuck` fires if a host stays in one step for two hours.

Local checks use fake bundles and processes without GPUs or production access:

```sh
python3 product/inference/gpu/host_bundle_test.py
python3 tools/gpu/pin_host_test.py
(cd tools/virtual-kubelet && go test -race ./... && go vet ./...)
docker buildx bake -f product/inference/bundles/build.hcl verify-host
```

The rejoin end-to-end test runs the gpu-fleet operator's rollout engine and
enrollment against the real GPU base image (only `nvidia-smi` is faked), the
real Tailscale client and Tailscale SSH, on a private tailnet run by headscale,
with RunPod faked so a re-image recreates the container. It enrolls a new host,
re-images it, restarts the operator mid-rollout, and checks the host rejoins
under the same instance and the exact `gpu-<id>` name, reached by that MagicDNS
name. Headscale keeps a node through re-authentication rather than making a new
device, so Tailscale's new-device rule and its `-1` renaming are covered by the
stateful Tailscale fake in the rollout tests, and in production by the spare
host's re-image, which goes first. The test's headscale adapter stands in for
the Tailscale API calls (`releaseInstanceName`, `claimInstanceName`, key minting
and revocation) and reads the sidecar with `tailscale status` rather than
`localStatus`; those are covered by the stateful fake too. Only an image built
by `e2e_image.py` contains `/etc/gradiated/test-control-server`, without which
`gradiated-host` ignores `GRADIATED_TAILSCALE_LOGIN_SERVER`.

```sh
python3 product/inference/images/gpu-base/tests/e2e_image.py /tmp/gpu-fleet-e2e
(cd product/services/gpu-fleet && GPU_FLEET_E2E=/tmp/gpu-fleet-e2e pnpm exec vitest run --config vitest.e2e.config.ts)
```

### Reserving an isolated qualification slot

Before running an unmanaged TP1 test beside serving allocations, use the merged
`tools/gpu/qualification-slot.py` with `AWS_PROFILE=gradiated-developer` to
`acquire --node gpu-<instance UUID> --lease .agents/runtime/qualification-lease.json`.
It requires a Ready, schedulable node with a spare GPU, 16 CPUs and 224 GiB RAM,
cordons it without evicting existing pods, and requires thirty seconds of stable
scheduled demand after the cordon, with a two-minute settling deadline. Capacity
and cordon ownership are rechecked every five seconds. The test must independently verify an unused GPU and hold its host GPU lock,
impose CPU/RAM limits, use private ports and enforce a cleanup deadline. No provider changes
are needed. The host reserved for the other workstream is rejected.

The lease file is recovery state. After confirming that the owned test processes
have stopped and their GPU/cgroup resources are released, run the same tool with
`release --lease .agents/runtime/qualification-lease.json`. It refuses to uncordon
a replaced node or a node whose qualification/fleet ownership changed. A command
failure or lost workspace leaves the node reserved; inspect the recorded owner
and finish cleanup before releasing it. This does not interrupt serving pods.
