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

Use Go 1.26.11, matching the compiler pinned in CI and the controller builder
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

Each pool in `models.json` names its runtime digest, GPU type, deadline and
rollout limits; see [pools and slots](#pools-slots-and-autoscaling). The renderer
supplies the common canary strategy, qualification, service account, drain
period and resources from the runtime catalogue. `max_surge` defaults to one and
`max_unavailable` to zero; a packed pool such as GLM sets `max_surge: 0` and
`max_unavailable: 1` to replace one replica at a time without a spare GPU.
Actual parallel startup depends on spare GPU, CPU and memory capacity.
Rollouts have no manual pause: the default canary moves to half weight, runs
SDK analysis and then completes. `rolling_update: true` moves directly to the
target revision without that half-weight canary. Per-pod SDK qualification still
gates readiness, and the rollout retains its final SDK analysis. Do not edit
generated Rollouts directly. Non-inventory fields in controller and RBAC
manifests remain editable; rendering preserves them. CI checks that generated
fields match the inputs. Remove a retired host Service or pool Rollout
explicitly after draining its workloads; rendering and --check fail if retired
resources remain.

## Argo CD applications

Each pool is its own Argo CD application, so one pool's sync, health or
pruning never waits on another. `render-config.py` writes each pool's Rollout,
disruption budget and ScaledObject to `gpu-inference/models/<pool>/`, and the
`gpu-models` ApplicationSet (`platform/gpu-models.yaml`) creates a
`gpu-model-<pool>` application for every such directory from one template;
adding a pool is a new directory. Two plain applications read the rest of `gpu-inference/`:
`gpu-fleet` (the `GpuHost` CRD and objects, the operator and its pins) and
`gpu-platform` (everything else: the namespace, gpu-controller, credentials,
RBAC, the training priority class and qualification). `gpu-fleet` creates the
namespaces it deploys into, but the operator can cordon nodes only once
`gpu-platform`'s `rbac.yaml` has synced.

Removing a pool is explicit, because deleting its directory deletes its
application but leaves the Rollout serving (`preserveResourcesOnDeletion`).
To stop a pool but keep its definition, set `max_replicas: 0` instead.

1. Withdraw the pool from traffic, for example with `max_replicas: 0`.
2. Remove it from `models.json` and delete `gpu-inference/models/<pool>/` in
   the same change, render and merge.
3. Wait until Argo has deleted the `gpu-model-<pool>` application; its Rollout
   keeps running, no longer managed. Deleting it earlier would let the
   application's self-heal recreate it.
4. Run `kubectl -n gpu-inference delete rollout,scaledobject,pdb <pool>`. Its
   pods stop with their normal termination grace period.

## Pools, slots and autoscaling

`models.json` maps each public model to `min_slots` and its pools. A pool is one
Rollout: one runtime release on one GPU type. A slot is one concurrent request
a replica admits: the runtime's enforced `active_requests`, or the pool's
`slots` for a runtime that enforces none (such as Kev). The same
limit weights gateway routing, so pools of different GPUs share one model's
traffic in proportion to their slots.

```json
"dealignai/glm-5.3-flash-uncensored": {
  "min_slots": 24,
  "pools": {
    "glm-dealign-sglang": {"runtime": "722c…", "gpu": "B300", "max_replicas": 5, "progress_deadline_seconds": 5400},
    "glm-dealign-sglang-h200": {"runtime": "130e…", "gpu": "H200", "max_replicas": 0, "progress_deadline_seconds": 5400}
  }
}
```

A pool may set `runtime`, `gpu`, `gpu_count`, `reservation`, `spread`
(`required` or `preferred` one replica per host), `slots`, `max_replicas`,
`mode`, `replicas`, `progress_deadline_seconds`, `max_surge`, `max_unavailable`,
`rolling_update`, `labels` and `annotations`. The renderer rejects anything
else, so a model cannot pin instance IDs or carry its own affinity.

Production pools fill in the order listed, so list the cheapest slots first.
The renderer turns `min_slots` into each pool's replica floor, filling earlier
pools to their maximum before later ones get any. The floor is the KEDA minimum
and the Rollout's initial count; a production pool with a floor of two or more
gets a disruption budget one below it. `max_replicas: 0` switches a pool off:
Argo holds its Rollout at zero and it has no autoscaler. A pool with a floor of
zero scales to zero after thirty minutes without demand, and a chat model is
served through OpenRouter meanwhile. OpenRouter cannot serve SystemOne, so the
renderer requires positive `min_slots` for SystemOne models such as Kev.
OpenRouter's own traffic to us never falls back, so it fails while a model has
no capacity of ours.

Every pool scales on the same three signals, in its own slots, and the HPA takes
the largest (a pool with no floor has a fourth, below):

- **Utilization.** The model's peak in-flight generations over the last minute
  (`gradiated:model_busy_slots`), divided by 0.7, less the slots the pools ahead
  of this one serve: a pool still growing counts at its maximum, and one that
  requests its maximum counts only its ready replicas, so demand it cannot place
  or serve passes to the next pool. In-flight generations include those
  OpenRouter serves, so demand stays visible while our pools are full or at
  zero.
- **Refusals.** While our own capacity refuses more than 5% of the model's
  requests for being full (`gradiated:model_capacity_refusal_ratio`), the pool
  asks for one replica more than it has ready (10% more above ten replicas),
  so capacity grows one replica at a time as each finishes loading. Refusals
  are routing capacity rejections, moves to OpenRouter for capacity and our
  `capacity_exceeded` failures, over admissions plus routing rejections.
  Customer balance and concurrency policy rejections do not count. A pool steps
  up on refusals only once every pool ahead of it requests its maximum, so a
  pool that cannot place its replicas hands demand on.

There is no CPU, memory or GPU-memory signal. Both recording rules live in
`workloads/observability/autoscaling-prometheus-rules.yaml`; the scaling
constants live in `tools/gpu/render-config.py`. All queries require fresh,
complete gateway telemetry. Missing samples or a Prometheus outage trigger a
fallback that retains the current replica count when it exceeds the floor.
Scale-up adds every replica the signals ask for at once, at least doubling or
adding four every 15 seconds, because a start takes minutes; scale-down waits ten minutes and
removes one at a time: a third signal, `draining`, holds the requested count
while any of the pool's replicas is terminating, because it can still hold its
GPUs, so the next removal waits only as long as the actual drain. New replicas
become available only after SDK qualification, so keep the floor large enough
for immediate traffic. None of this provisions or resets a provider GPU, and
scaling down releases GPUs without reducing the RunPod reservation bill.

A pool with no floor may be at zero replicas when a new revision lands, so its
canary analysis would have nothing to qualify. While its Rollout updates, a
fourth signal, `qualifying`, asks for one replica, and the pool moves straight
to the new revision rather than through a half-weight canary, which at one
replica would also restart the previous runtime. That replica must pass SDK
qualification; if no host can take it, the analysis times out and the Rollout
aborts. Once the update completes, an idle pool returns to zero after the
usual cooldown.

### Startup state labels

Each GPU node carries labels saying what a runtime it already pins needs
to start is already on the host's disk, so model pods can prefer hosts that
start faster. `<rt>` is the first 16 hex characters of the runtime's key in
`product/inference/gpu/runtimes.json`:

- `gradiated.com/bundle.<rt>=true`: the runtime's bundle for the host's base is
  staged under the host agent's `bundles/` directory.
- `gradiated.com/weights.<rt>=true`: every pinned model repository of the
  release is in the host's Hugging Face cache at the pinned revision. The host
  checks this offline: the snapshot has `config.json` and every shard its
  `model.safetensors.index.json` names (or a `model.safetensors`), and the
  repository has no `.incomplete` blob. A repository without safetensors never
  counts as present.

The host agent recomputes these parts from disk at start and every 60 seconds in
housekeeping, and returns the last result to the `startup_parts` operation. The
gpu-controller reads them every 60 seconds per host and patches the node: it
adds missing labels and removes `gradiated.com/bundle.*` and
`gradiated.com/weights.*` labels the host no longer reports, leaving every other
label alone. A frozen recovery agent rejects the operation and so reports no
parts. If the host cannot be read, the labels stay as they are, so a
missed pass or a manual edit is corrected by the next successful one.

### Reservations

A host is reserved with a `gradiated.com/reserved=<name>` `NoSchedule` taint in
`hosts.yaml`. A pool with `"reservation": "<name>"` tolerates it and is
confined to exactly the hosts carrying it; the renderer derives that host list,
so adding a host to a reservation is a `hosts.yaml` change. Kimi K3.1 Pro
reserves both eight-B300 hosts as `kimi-k31`; every other host is shared. A
tensor-parallel replica needs all its GPUs on one host; `gpu_count` selects
hosts by size.

Training runs opportunistically on shared capacity. Training Jobs use the
`gpu-training` PriorityClass, below the default priority of model pods, so a
model replica that cannot fit preempts training rather than waiting; training
never preempts. A preempted trainer resumes in a new Job from its latest S3
checkpoint, with up to three attempts per training stage. Its pod directory is
retired with the pod, so local disk is scratch: work since the last checkpoint
is lost. To hold capacity for training that must not be preempted, give a host
the `training` reservation, which training Jobs tolerate and models cannot use.

### Staging a pool

A pool with `"mode": "qualification"` and a fixed `replicas` count runs a
private runtime model ID. It passes SDK qualification but is never routed,
scaled by demand, counted in the floor or alerted on; test it with the
`x-gradiated-deployment-id` header. It keeps a fixed autoscaler so the fleet
operator can surge it during a host re-image. Promote it by replacing `mode` and
`replicas` with `max_replicas`, which places it in the fill order. The GLM and
Kimi helpers in `tools/gpu/` stage and promote their pools this way.

### Availability alerts

Alerts use the rendered floors and the Rollouts' requested counts. No ready
replica of a model with a positive floor alerts after one minute, and falling
below the floor after thirty seconds. A pool's alert floor allows the
`max_unavailable` replicas a rollout replaces at once, but never drops below one
replica, so a one-at-a-time replacement does not warn. Requested capacity that stays unready for
twenty minutes, including a scale-up from zero, has a separate warning.

### GPU scheduler

EKS runs `default-scheduler` in its managed control plane with a fixed profile
that scores nodes `LeastAllocated`, so it spreads pods: a TP2 pod can take an
empty 4-GPU host and leave no whole host for a TP4 or TP8 pod. The
`gradiated-gpu` scheduler (`gpu-inference/gpu-scheduler.yaml`) is a second,
upstream `kube-scheduler` in `gpu-inference`, two replicas behind a leader
lease. Its one profile keeps the default plugins but scores `NodeResourcesFit`
`MostAllocated` on `nvidia.com/gpu` only, so the fullest host that still fits
wins and a TP2 pod takes a free 2-GPU host first. `NodeAffinity` has weight 10
against packing's 1, so a preferred node affinity (a warm host, say) outranks
packing. Pods opt in with `schedulerName: gradiated-gpu`; any other pod keeps
`default-scheduler`. `GpuSchedulerUnavailable` warns when it has no ready
replica for ten minutes.

## Rollout alerts

`GpuRolloutFailed` warns when Argo Rollouts reports a Rollout as `Abort`,
`Timeout`, `Error` or `InvalidSpec`: it aborted at its progress deadline, failed
SDK qualification, or cannot reconcile. It does not retry automatically. Free
capacity if needed, then run `kubectl argo rollouts retry rollout <name> -n
gpu-inference` or push a fix. `GpuRolloutBlocked` warns when a model pod has had no
GPU host for 15 minutes, before the deadline aborts the rollout. To free capacity,
lower another model's `min_slots` or a pool's `max_replicas` in `models.json`, or
pin it temporarily with the ScaledObject's `autoscaling.keda.sh/paused-replicas`
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
  model ever has fewer Ready replicas than it had. A model listed in
  `RETIRE_ON_REIMAGE` (`product/services/gpu-fleet/src/rollout.ts`; currently
  empty) is not moved: once its
  other replicas are Ready elsewhere, its pods on the host are marked first and
  its count lowered by that many, and the host blocks if that would leave the
  model with no replica. Such a model needs no room elsewhere to proceed. Resume
  KEDA; re-image the pod
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
(`gradiated_gpu_host_*`), so existing alerts are unchanged;
`GpuHostRolloutStuck` fires if a host stays in one step for two hours. It also
exports each host's GPUs labelled with its state
(`gradiated_gpu_fleet_host_gpus`: `in_pool`, `reserved`, `cordoned` by a
person, `leasing`, `leased`, `returning`, `updating` or `degraded`), the GPUs each workload's pods request on
each host (`gradiated_gpu_fleet_host_workload_gpus`), each lease's holder,
purpose and start, and lease outcomes
(`gradiated_gpu_fleet_lease_events_total`: `granted`, `released`, `expired`,
`preempted`, `failed`, `return_failed`). The
[GPU Fleet dashboard](https://grafana.gradiated.com/d/gradiated-gpu-fleet)
charts them with model slots, replicas and autoscaling signals, and the GPU host
and fleet alerts link to its panels.

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

### Leasing a host

Hand-run work, such as training on sensitive data, leases a whole host; a host
is never shared between a lease and serving or training pods. The gpu-fleet
operator does the work and `tools/gpu/host-lease.py` writes the request, the
`fleet.gradiated.com/lease` annotation on the `GpuHost`
(`{"holder", "purpose", "until", "preemptible"}`):

```sh
python3 tools/gpu/host-lease.py acquire 01a0f19d --hours 6 --purpose "SFT sweep" [--no-preempt]
python3 tools/gpu/host-lease.py wait 01a0f19d     # until the host is leased, or the lease fails
python3 tools/gpu/host-lease.py extend 01a0f19d --hours 2
python3 tools/gpu/host-lease.py release 01a0f19d  # hand it back early
python3 tools/gpu/host-lease.py status
```

- A lease rollout first checks the request and the host, and refuses reserved
  hosts (a `gradiated.com/reserved` taint), hosts that do not answer or have
  no node, nodes already cordoned (by a person, a qualification slot or a
  failed rollout), hosts whose rollout is blocked waiting for room, and pods
  with a RunPod volume, which a re-image keeps (Kev's RTX host `01a0f1bc` and
  both Kimi hosts have one). An operator in observe mode, or without RunPod and
  Tailscale access, refuses every lease. It then cordons the host
  and moves its model replicas onto free GPUs on other hosts, as a re-image
  does, drains it and records `status.lease`. It does not rearrange other
  hosts' pods to make room. If the replicas have no room, a training job runs
  there, or a replacement replica finds no host, the lease fails at once and
  the host stays in the pool.
- Each request is tried once. The operator records the outcome on
  `status.rollout` (with the request in `rollout.lease`) and removes the
  annotation, so the host is planned like any other again; run `acquire` again
  to retry. A failed lease never holds up the fleet's other rollouts, and the
  retry annotation does not apply to it. A failed lease does not mark the host
  Degraded. A lease waits its turn behind a
  rollout that is running, but not behind one waiting for capacity.
- While leased, the host is cordoned, cordoned again if someone lifts it or the
  node is recreated, and the operator does nothing else to it: no re-image,
  bundle update or recovery. Autoscaling has one host fewer, and
  overflow goes to OpenRouter.
- A lease is preemptible unless requested with `--no-preempt`
  (`"preemptible": false`). Once a model replica that would fit on a
  preemptible leased host has found no host for ten minutes, counted from the
  last rollout to finish, the operator returns that host, the one due back
  soonest first, and the replica lands there after the return. The holder gets
  no warning beyond `status`. A re-image waiting for room does not preempt a
  lease; it waits for the lease to end.
- Removing the annotation hands the host back; reaching `until` does the same,
  and a request from a different holder is treated as a hand-back followed by
  a new lease, so the host is wiped between holders.
  A return rollout re-images the RunPod pod onto the pinned image, which
  recreates its container disk and so removes everything the holder left, then
  enrolls, verifies, soaks and uncordons it. A return runs even while another
  rollout waits for capacity, since it adds a host. A return that cannot run
  fails rather than blocks, so the host stays cordoned until it is wiped, and
  is retried once the pins change or the retry annotation is set;
  `GpuHostLeaseOverdue` warns an hour after an unreturned lease expires or its
  return starts. The tool caps a lease at seven days, and writes each change
  only if the `GpuHost` is unchanged since it was read, so two holders cannot
  both acquire it.

The host keeps its management key across the return. A holder with root could
read it, so rotate it by hand after leasing a host that ran untrusted code;
rotating it automatically needs `secretsmanager:PutSecretValue` for the
operator. The `$gpu-host-lease` skill has the procedure for agents. Active
leases, their time left and their outcomes are on the
[GPU Fleet dashboard](https://grafana.gradiated.com/d/gradiated-gpu-fleet).

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
