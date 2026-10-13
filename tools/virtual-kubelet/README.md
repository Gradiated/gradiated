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

`cmd/kev-controller` watches the `gpu-inference` namespace. Three controller
replicas run on separate EKS nodes and elect one leader. Host operations carry a
fencing epoch so a replaced leader cannot continue changing workloads.

Each RunPod host advertises its GPU count, CPU budget, memory budget and GPU
model. Kubernetes places a pod using those resources and its node selector.
The host agent assigns physical GPU UUIDs, takes exclusive GPU locks, and puts
the pod's processes in a cgroup with CPU, memory and process limits. It refuses
a GPU that already has a compute process. Tensor-parallel and single-GPU
workloads can share a host without sharing a GPU claim.

`runtimes.json` pins the supported bundles and their execution settings. The
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
cleanup retains the claim. Process birth times prevent signalling a reused PID.

Controller, agent and proxy restarts retain model processes. A host reset loses
node-local state and requires enrollment again; it must not be used as a
migration or recovery step on a retained reservation.

## Enrollment and checks

Enrollment stages and verifies the permitted runtime bundles, then installs
`host-agent.py`, `supervise.py`, Desmond and the root-only configuration using
`install-host.py`. The controller's host inventory and named node/lease RBAC
must include the instance, and its management key belongs in the
`gradiated/prod/platform/gpu-controller` AWS secret. Argo owns the corresponding
Kubernetes resources under
`infra/environments/prod/us-east-1/kubernetes/gpu-inference`.

During the Nomad migration, disable Nomad placement before enrolling a host and
wait for every old workload to drain. Never allow both schedulers to assign the
same GPUs. Enrollment changes files and processes over pinned SSH, without
changing RunPod provider settings or releasing the reservation.

Run the local adapter checks with:

```sh
cd tools/virtual-kubelet
go test -race ./...
go vet ./...
python3 host_agent_test.py
python3 remote_test.py
```

The default `gpu-base` image runs `product/inference/gpu/bootstrap.py`. Its
`GRADIATED_GPU_BOOTSTRAP` value is a base64 JSON envelope supplied at pod
creation: instance UUID, host-management key, one-time GPU-tagged Tailscale
auth key, private API tailnet address, and the permitted runtime configuration.
The process clears the bootstrap environment before starting services. It
receives no OAuth, Kubernetes, database or AWS access credential. Bundle
downloads use temporary grants from the private control bridge. Keep bootstrap
values outside the repository.

`main.go` and `remote.py` are the original isolated SSH lifecycle experiment.
They are not the production controller or host agent.
