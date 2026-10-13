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

Pinned direct SSH is required. Configure `runpod-ssh-key` and
`runpod-ssh-host-keys` in the ops MCP secret. A running provider pod keeps its
image, environment, ports, and GPU reservation. An already enrolled host is
checked without replacing its workloads. A new host must have the verified GPU
base implementation and idle GPUs. Stopped pods use the pinned `GPU_BASE_IMAGE`;
changing any running pod's provider settings requires explicit reset authorization.

Commit the prepared result:

1. Put `privateService` under the Tailscale host Services.
2. Add `kubernetes.host` to `gpu-inference/controller.yaml`'s `hosts.json`.
3. Add `kubernetes.managementSecret` to the controller ExternalSecret when it
   refers to a separate host secret. The existing fleet secret remains projected
   for the first six hosts.
4. Add the `gpu-<instance UUID>` name to the controller's named Node and Lease
   permissions. Update the inventory checksum annotation to restart the controller.
5. Let Argo sync, then verify that the Node is Ready and advertises the measured
   GPU, CPU and memory budget before scheduling work.

This explicit Git step keeps enrollment from giving the operations service broad
Kubernetes write access. Three controller replicas run on separate EKS nodes;
leader fencing prevents two controllers from changing the same host concurrently.

## Credentials and traffic

The GPU receives a one-time, GPU-tagged Tailscale enrollment key and its own
management key. OAuth, Kubernetes, database and AWS administrative credentials
remain in EKS. A root-owned management key protects privileged host operations
from unprivileged model processes. It is separate from customer authentication.

Model traffic uses the private `gpu-<instance UUID>` Service and Tailscale.
Desmond and adapter downloads use the private GPU control bridge. Runtime bundles
use short-lived signed downloads issued by that listener. GPUs have no grant or
VPC route to PostgreSQL, Valkey, the Kubernetes API, or unrelated internal services.
The [Tailscale guide](../infra/modules/tailscale/README.md) defines the network policy.

Provider resets destroy local state. Do not reset an allocated GPU to update
software. Apply host-agent updates over pinned SSH without changing active runtime
profiles; model updates belong in Kubernetes Rollouts.

## Deploy and verify a model

Update its pinned bundle and release metadata in the GPU runtime catalogue and
its Rollout under `infra/environments/prod/us-east-1/kubernetes/gpu-inference/`.
Stage the verified bundle on eligible hosts before changing the Rollout. The
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
