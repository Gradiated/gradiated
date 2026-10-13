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

Deleting a previously qualified inference pod withdraws new traffic, allows
existing requests eleven minutes to finish, stops its processes, and verifies
that its cgroup is empty before releasing GPU claims. Unqualified canaries and
training pods stop without that inference drain. Kubernetes pod deletion is
completed after host cleanup; it does not add another grace period. Failed
cleanup retains the claim. Training data and per-pod LoRA caches are removed
after processes stop; diagnostic logs remain on the host. Process birth times
prevent signalling a reused PID.

Controller, agent and proxy restarts retain model processes. A host reset loses
node-local state and requires enrollment again; it must not be used as a
migration or recovery step on a retained reservation.

## Enrollment and checks

Enrollment stages and verifies the permitted runtime bundles, then installs
`host-agent.py`, `supervise.py`, Desmond and the root-only configuration using
`tools/gpu/install-host.py`. Add the registration's `kubernetes.inventoryEntry` to
`infra/environments/prod/us-east-1/kubernetes/gpu-inference/hosts.json` and run
`python3 tools/gpu/render-config.py` (requires PyYAML 6.0.2). This generates the
private Service, controller inventory/checksum, host key projection and named
Node/Lease RBAC. The inventory stores secret references, never key values.
Argo owns the resulting manifests; review them before scheduling a new host.

All production serving replicas and training Jobs use Kubernetes. Existing
RunPod containers retain a suspended legacy main process only to preserve their
reservation; it has no jobs or cluster access. New hosts use the GPU base image.

Run the local adapter checks with:

```sh
cd tools/virtual-kubelet
go test -race ./...
go vet ./...
python3 host_agent_test.py
```

The default `gpu-base` image runs `product/inference/gpu/bootstrap.py`. Its
`GRADIATED_GPU_BOOTSTRAP` value is a base64 JSON envelope supplied at pod
creation: instance UUID, host-management key, one-time GPU-tagged Tailscale
auth key, private API tailnet address, and the permitted runtime configuration.
The process clears the bootstrap environment before starting services. It
receives no OAuth, Kubernetes, database or AWS access credential. Bundle
downloads use temporary grants from the private control bridge. Keep bootstrap
values outside the repository.

Model catalogue changes are rendered into the controller ConfigMap by
`python3 tools/gpu/render-config.py`. The controller asks each host to stage the
pinned bundles through private download grants. Downloads run outside the host
operation lock; activation and pod creation share a lock. Active runtime profiles
remain unchanged until their pods drain. Select the runtime and placement in `gpu-inference/models.json` alongside the
catalogue; an unstaged candidate retries while existing replicas keep serving.
The controller image is built and pinned by the normal application release.

The model configuration names the runtime digest, replica count, deadline and
placement. The renderer supplies the common canary strategy, qualification,
service account, drain period and resources from the runtime catalogue. Do not
edit generated Rollouts directly. Non-inventory fields in controller and RBAC
manifests remain editable; rendering preserves them. CI checks that generated
fields match the inputs. Remove a retired host Service or model Rollout explicitly after draining
its workloads; rendering and --check fail if retired resources remain.

## Model autoscaling

KEDA owns each Rollout's replica count through the standard Kubernetes scale
API. Argo CD ignores only `spec.replicas`; it still reconciles model releases,
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
and base compatibility ID. Host bundles contain the agent, state and staging
helpers, Desmond, and its startup script. The control bridge stays in the base.
The base keeps SSH, enrollment, Tailscale, downloader, nginx, the launcher
(`supervise.py`) and a frozen recovery agent under `images/gpu-base/recovery/`. Ordinary agent
and staging changes build only the host bundle; they do not invalidate the base
or model bundles. Refresh the recovery sources with
`python3 tools/gpu/refresh-recovery.py` only for a deliberate, qualified base
release. Host releases do not require re-pinning or replacing a reservation.

`gpu-inference/host.json` is initially `null`: legacy hosts continue serving and
no host software update is requested. After installing the launcher on retained
hosts, pin a **host** release artifact and commit the generated configuration:

```sh
python3 tools/gpu/pin-host.py /path/to/host-runtime-release/release.json
python3 tools/gpu/render-config.py --check
```

The pin has `sha256` and `base_id` fields. A different base is rejected before
download. Hosts use the existing downloader and short-lived control-bridge grants. Root
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
agent or start the base recovery agent; new updates wait until state can be
committed. The agent exits if its launcher dies, while independent model workers
keep running. Current,
previous, one unused verified bundle, and code referenced by live task/proxy
workers are retained. This last exception preserves workers across successive
agent updates.

Argo CD reconciles the model Rollouts and the controller's host-bundle pin.
Argo Rollouts manages model pod updates; the GPU controller sequences host-agent
updates itself. Models and host agents run verified tarballs unpacked on disk.
Their Dockerfiles package and verify those artifacts in CI; the GPU provider
still starts hosts from a base container image.

A serial background controller worker observes every host before starting and
updates in `hosts.json` order. Node health checks and metric scrapes never wait
on rollout I/O. It requires five continuous minutes of model readiness with unchanged
serving process identities before advancing. A missing original serving pod also
stops the update, so concurrent model rescheduling cannot certify the host bundle. Staging has a 35-minute
deadline; its download time does not consume the health grace or serving soak.
Continuous agent or model health failure has a separate two-minute limit; an updated host that remains unreachable or unready stops the rollout.
One node annotation (`gradiated.com/host-bundle-update`) checkpoints the release,
phase, original process identities and deadline before staging. A new leader
resumes that host and repeats the full soak while retaining the baseline and
deadline. Failure annotation and event writes retry on API outages. Ambiguous
configure responses retry on the same host. The health grace measures continuous
failure separately from download time and resets when health returns. `GpuHostUpdateFailed` events
and alerts stop the fleet update; repair the bundle and pin a new digest. To
revert, pin a previously healthy release. A failed digest requires deliberate
operator investigation before clearing its launcher failure and node annotation.
The recovery `ping`, `claim` and `configure` operations and additive on-disk
state must remain compatible with every still-pinned base agent indefinitely;
one-release compatibility applies only to the remaining API.

The controller's `/metrics` exposes running/previous digest information, drift
from the Git pin, and rollout failure. The controllers dashboard shows host
versions only while host observations are fresh, and a separate panel shows
telemetry age. Drift alerts after 24 hours; stale host telemetry and missing
controller scrapes also alert.

### One-time retained-host migration

Prepare an explicit JSON list of SSH targets outside version control, for example
`[{"instance_id":"<inventory UUID>","ssh":"root@gpu-host","port":22}]`.
Build the host artifact to obtain its Linux `desmondd`, and confirm each retained
host's OS/CUDA compatibility ID before running:

```sh
python3 tools/gpu/rollout-host.py --targets /path/to/targets.json \
  --desmondd /path/to/desmondd --base-id ubuntu24-cuda13-amd64-v2
```

This is a production operation requiring operator authorization. The command
checks enrolled identity, staged runtime digests, and live model/reporter/proxy
process identities; installs the recovery agent and launcher; and stops at the
first failed host. It reads the management credential on the remote host and
never outputs it. Known SSH host keys are required. The existing supervisor may
be PID 1: it stays running and its SIGHUP path launches a shim that execs the new
launcher. No provider restart or image change is involved. Re-running the
command signals the same supervisor. Hosts already using a direct launcher keep
their agent entrypoint; the recovery directory is selected at each restart. New
hosts obtain the launcher from the
base image when its published digest is separately approved and pinned.

Local checks use fake bundles and processes without GPUs or production access:

```sh
python3 product/inference/gpu/host_bundle_test.py
python3 tools/gpu/rollout_host_test.py
(cd tools/virtual-kubelet && go test -race ./... && go vet ./...)
docker buildx bake -f product/inference/bundles/build.hcl verify-host
```
