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

Commit the prepared result by adding `kubernetes.inventoryEntry` to
`infra/environments/prod/us-east-1/kubernetes/gpu-inference/hosts.json`.
Run `python3 -m pip install PyYAML==6.0.2` once, then
`python3 tools/gpu/render-config.py` from the repository root. The renderer
projects the private Service, controller inventory/checksum, secret reference
and named Node/Lease permissions. Review and commit the generated manifests.
Let Argo sync, then verify the Node is Ready with measured GPU, CPU and memory
budgets before scheduling work.

`inference-hosts` automatically reconciles generated host Services, while
`gpu-inference` reconciles inventory, credentials and permissions. Shared proxy
changes remain manually deployed through `inference-network`. A transient delay
between these Applications is retried by the GPU controller. A missing Service
lasting five minutes raises `GpuHostServiceMissing`; do not wait for a model
Rollout deadline to diagnose enrollment. Automatic pruning is disabled for host
Services, so retirement still requires explicit cleanup after draining workloads.

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

Provider resets destroy local state. Do not reset an allocated GPU to update
software. Host-agent updates are host bundle pins, which the controller rolls out one host
at a time without changing active runtime profiles; model updates belong in
Kubernetes Rollouts.

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

Training uses Kubernetes Jobs and the same host agent. Temporal owns attempts,
leases, artifact grants and cleanup. The gateway still uses the PostgreSQL
inventory and existing KV-cache routing; it does not need to know the scheduler.
See the [RunPod Kubernetes guide](../tools/virtual-kubelet/README.md) for supported
execution, recovery and limitations.
