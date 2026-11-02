# GPU enrollment and Kubernetes deployment

GPU hosts belong to the EKS cluster. RunPod exposes a container with attached
GPUs, so the GPU controller represents each enrolled host as a Kubernetes Node
through Virtual Kubelet. The host agent runs our pinned model and training
bundles. Bare-metal hosts can use a normal kubelet instead.

## Enroll a host

Use the private administrative ops MCP connection described in the
[operations README](../product/services/ops-mcp/README.md#private-administrative-tools):

```text
register_instance(provider: "runpod", instance_id: "<provider pod ID>")
instance_registration_status(registration_id: "<returned ID>")
```

Registration records the provider identity and stable instance UUID, prepares
the GPU host agent, and joins Tailscale. Status moves through `recording`,
`updating_provider`, and `prepared`, or `failed`. The result contains public
configuration and secret references, never credential values.

GPU hosts have no public SSH. A new pod uses the v5 RunPod template: the GPU base
image, no exposed TCP 22, and a single-use `tag:gpu-bootstrap` Tailscale key from
the RunPod secret `gradiated_tailscale_bootstrap` (minted with
`tools/gpu/mint-bootstrap-key.py` immediately before creating the pod). On first
start the pod joins the tailnet as `gpu-bootstrap-<pod ID>` with Tailscale SSH and
no network grants. ops-mcp reaches it through its own `tag:ops-mcp` Tailscale
sidecar, which may open Tailscale SSH only to bootstrap pods. Registration installs
the host agent over that session and then re-authenticates the pod as
`tag:gpu-inference`, which ops-mcp cannot reach. A running provider pod keeps its
image, environment, ports, and GPU reservation. An already enrolled host is
checked without replacing its workloads. A new host must have the verified GPU
base implementation and idle GPUs. Enrollment never uses public SSH. Changing any
running pod's provider settings requires explicit reset authorization.

To move an existing pod onto v5, register it with `reset_running_pod: true` and
its ID in `confirm_instance_id` (a stopped pod needs neither). ops-mcp mints the
pod's own single-use bootstrap key, re-images the pod with the approved GPU base
image, no exposed ports and that key in its environment, waits for it to join,
and enrolls it as above; nobody handles the key. The reset stops the pod's
workloads, so drain a serving host first.

Commit the prepared host as a `GpuHost` in
`infra/environments/prod/us-east-1/kubernetes/gpu-inference/hosts.yaml`: its
instance ID, RunPod account and pod ID, measured inventory and management secret
reference. Run `python3 -m pip install PyYAML==6.0.2` once, then
`python3 tools/gpu/render-config.py` from the repository root, which projects the
controller's host list, secret reference and named Node/Lease permissions. Let
Argo sync, then verify the Node is Ready with measured GPU, CPU and memory budgets
before scheduling work. Merge the `GpuHost` within a day of registering: the
operator retires an `instances` row of the fleet's RunPod account that has had no
`GpuHost` for 24 hours, and restores it when the `GpuHost` arrives.

The `gpu-fleet` operator creates the host's private Service, records the host in
the PostgreSQL `instances` table and reports its health in the `GpuHost` status,
which Argo shows on the `gpu-fleet` application. Shared proxy changes remain
manually deployed through `inference-network`. A missing Service lasting five
minutes raises `GpuHostServiceMissing`, and a Degraded host raises
`GpuFleetHostDegraded`; do not wait for a model Rollout deadline to diagnose
enrollment.

To retire a host:

1. Remove it from `hosts.yaml`, run `python3 tools/gpu/render-config.py` and
   merge. Argo then stops wanting the `GpuHost`, and does not prune it; the
   renderer keeps the host's node permissions and management key.
2. `kubectl delete gpuhost gpu-<instance id>`. The operator cordons the node and
   holds the deletion until no pods run on it, so drain its workloads.
3. Once the `GpuHost` is gone, run
   `python3 tools/gpu/render-config.py --retire <instance id>` and merge, which
   drops the host's access.
4. Delete its Service in `tailscale-inference` by hand; the operator never
   deletes Services. Its PostgreSQL row is retired a day later.

This explicit Git step keeps enrollment from giving the operations service broad
Kubernetes write access. Three controller replicas run on separate EKS nodes;
leader fencing prevents two controllers from changing the same host concurrently.

## Credentials and traffic

The GPU boots with a single-use `tag:gpu-bootstrap` key, then receives a one-time,
GPU-tagged Tailscale enrollment key over Tailscale SSH and its own management key. OAuth, Kubernetes, database and AWS administrative credentials
remain in EKS. A root-owned management key protects privileged host operations
from unprivileged model processes. It is separate from customer authentication.

Model traffic uses the private `gpu-<instance UUID>` Service and Tailscale.
Desmond and adapter downloads use the private GPU control bridge. Runtime bundles
use short-lived signed downloads issued by that listener. GPUs have no grant or
VPC route to PostgreSQL, Valkey, the Kubernetes API, or unrelated internal services.
The [Tailscale guide](../infra/modules/tailscale/README.md) defines the network policy.

Host software changes are pins in `gpu-inference/pins.json`. The `gpu-fleet`
operator rolls them out one host at a time: a new host bundle in place, without
restarting serving processes; a new GPU base image by moving the host's pods to
other hosts first, then re-imaging and re-enrolling it. A provider reset destroys
local state, so only the operator's drained rollout resets pods; model updates
belong in Kubernetes Rollouts. See
[the GPU controller guide](../tools/virtual-kubelet/README.md#rolling-hosts-onto-the-pins).

Administrators reach GPU hosts only with Tailscale SSH as root. The tailnet policy
allows it for tailnet admins in check mode, which repeats the Google sign-in with
MFA every 12 hours; Tailscale records each session. The
[RunPod guide](../infra/environments/prod/runpod/README.md#shell-access-and-recovery)
describes recovery and moving existing hosts.

## Deploy and verify a model

Update its pinned bundle and release metadata in the GPU runtime catalogue and
select it in `infra/environments/prod/us-east-1/kubernetes/gpu-inference/models.json`.
Run `python3 tools/gpu/render-config.py` to project the catalogue into the
controller ConfigMap. The controller stages and verifies bundles through private
download grants before accepting the new runtime. The
scheduler places replicas using resources, GPU-product labels and affinity.

Native runtime health sets `RuntimeReady`. The product worker then verifies the
specific process incarnation through the production SDK before marking it Ready
and making it available to gateway routing. Argo analysis checks that qualification
before promotion. Previously qualified pods drain existing requests before GPU
claims are released. Keep enough spare capacity for the replacement replica.

For the explicitly authorized GLM PD experiment on the two-B300 host
`gpu-01a19170-d2a0-74ca-b317-d87d69988e4b`, first run
`python3 tools/gpu/reserve-glm-pd-host.py` to inspect the reservation plan. After
the helper is merged and the operator authorizes reducing serving capacity, run
it with `--apply --lease .agents/runtime/glm-pd-host-lease.json`. Wait for Argo to
sync the generated `glm-dealign` disruption budget with `minAvailable: 8` first.
The helper requires its live UID and observed status, a healthy, stable
ten-replica rollout and eight other qualified Ready replicas,
cordons only that host, and evicts its two pinned GLM pods through their normal
drain and disruption budgets. It waits up to 15 minutes for both pod UIDs to
disappear before checking the free two-GPU experiment capacity; it never changes
the provider reservation or shortens request draining. Once experiment processes
have stopped and both GPUs are verified free, release the owned cordon with
`python3 tools/gpu/qualification-slot.py release --lease .agents/runtime/glm-pd-host-lease.json`.
Preserve the lease for recovery if cordon ownership changes or release fails.

### Manual model rollout pauses and GPU-size changes

Use Argo Rollouts to inspect, pause, promote and abort a model rollout. The model
ApplicationSet preserves `/spec/paused`, so Argo CD self-healing does not undo an
operator pause. Resume a manual pause by clearing only `spec.paused`. Use
`promote` only at an explicit pause step: promoting during analysis can advance
past that analysis, and `--full` skips all remaining analysis and pause steps.
A pause controls revision progression; it does not freeze HPA scaling or replace
the model configuration in Git.

```sh
kubectl argo rollouts get rollout glm-dealign-sglang -n gpu-inference
kubectl argo rollouts pause glm-dealign-sglang -n gpu-inference
kubectl patch rollout glm-dealign-sglang -n gpu-inference --type merge -p '{"spec":{"paused":false}}'
# Advance only when stopped at an explicit pause step.
kubectl argo rollouts promote glm-dealign-sglang -n gpu-inference
kubectl argo rollouts abort glm-dealign-sglang -n gpu-inference
```

A one-GPU to two-GPU migration is a capacity migration as well as an image
update. A two-GPU pod needs both GPUs, its CPU request and its memory request on
one eligible node. Free GPUs on different nodes cannot satisfy it. Changing ten
one-GPU replicas to ten two-GPU replicas doubles the requested GPUs; the same
GPU footprint instead requires five two-GPU replicas.

Keep the vLLM and SGLang Rollouts separate during this migration. Qualify the
existing two-GPU canary first. Before each expansion, select two co-located
vLLM allocations on a host that can fit the complete SGLang resource request,
arrange their normal drain through reviewed placement and replica changes, and
wait for their allocations to be released before adding one SGLang replica.
Check that remaining qualified capacity is sufficient throughout warmup. Do not
rely on a replica-count reduction to select a particular pair: Kubernetes may
choose pods on different hosts. Respect existing host exclusions and other models.

Pause at the intended initial exposure and observe routed availability, runtime
failures, TTFT, decode throughput and capacity rejections for at least 20 minutes
before the next manual promotion. Argo's replica weight is not an exact request
percentage for this gateway: routing uses direct pod endpoints and rendezvous
hashing, and mixed one-GPU/two-GPU pods have different capacity. A failed analysis
must remain a rollout failure; do not bypass it with full promotion. Argo abort
restores that Rollout's previous ReplicaSet, not replicas removed from a separate
Rollout, so a migration rollback must also restore the reviewed replica and
placement configuration with enough free capacity.

Training uses Kubernetes Jobs and the same host agent. Temporal owns attempts,
leases, artifact grants and cleanup. The gateway still uses the PostgreSQL
inventory and existing KV-cache routing; it does not need to know the scheduler.
See the [RunPod Kubernetes guide](../tools/virtual-kubelet/README.md) for supported
execution, recovery and limitations.
