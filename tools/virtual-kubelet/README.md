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
scrapes count), and capacity rejections. Each signal is scoped to the exact
model and summed across gateway replicas. The HPA takes the largest recommendation.
Capacity rejections request the configured ceiling; customer balance and
concurrency policy rejections do not. The initial concurrency targets are 0.7
for Kev's single execution slot and 16 for the batched runtimes. The batched
targets are conservative starting policy, not measured throughput guarantees;
tune them against time to first token and queue pressure under representative
traffic. GPU memory allocation alone is not a useful scale-down signal.

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
Training consumes the same finite GPU resources and can delay serving placement.
Scaling down a model releases GPUs but does not reduce the RunPod reservation bill.

## Recovery and disk limits

Host ownership records are written through a shared helper that fsyncs file data
before replacement and the parent directory before acknowledging success.
Process handles include boot and PID namespace identities as well as PID birth
times. Serving task recovery retains the pod UID and requires SDK qualification
of the new process incarnation. Training tasks that already started never retry
automatically. Unknown processes retain their GPU claims instead of allowing
another task to start. Child tasks are reaped; their cached process objects are
not durable workload state.

Every minute, cleanup preserves configured, active and staging bundles. It keeps
two verified unused bundles and at most twenty retired pod diagnostic directories
for up to seven days. Live processes or occupied cgroups prevent retirement; an
unrecorded live process blocks bundle cleanup. Model weights are not pruned.
Diagnostic logs are bounded at 32 MiB per file using copy/truncate of the recent
16 MiB, retaining the writer's inode. Concurrent log lines can be lost during
truncation; inference output and durable training artifacts use separate paths.

CI runs Go race/vet checks, a real Go-to-Python HTTP fencing test, host recovery
and cleanup tests, injected storage failures, process crashes around file
replacement, bootstrap checks and downloader checks. These simulate process and
storage failures without releasing GPU reservations. Physical host loss still
requires replacement capacity; a provider reset requires deliberate enrollment.
