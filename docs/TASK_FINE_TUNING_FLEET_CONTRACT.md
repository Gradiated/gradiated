# Fine-tuning: Kubernetes scheduling

Kubernetes is the only GPU scheduler. RunPod hosts appear as virtual Nodes;
bare-metal hosts use ordinary kubelets. PostgreSQL owns provider inventory,
model identity and artifact metadata. Git owns runtime pins, serving replicas
and placement. Kubernetes owns workload placement and lifecycle. The gateway
uses the existing deployment projection, not scheduler queries on the request path.

Serving uses one Argo Rollout per configured base runtime. Private adapters load
into compatible replicas rather than creating a deployment per adapter. Runtime
pins live in `product/inference/gpu/runtimes.json`; each model's pools, slots
and placement live in `gpu-inference/models.json`. The renderer projects resources and
release metadata into the production manifests.

Training creates deterministic Kubernetes Jobs from frozen run configuration.
Jobs have no automatic retry; Temporal owns attempts, capacity waits, leases,
checkpoint recovery and cleanup. Training is restricted to the configured
provider inventory and GPU product. Job deletion releases its processes and
GPU claims, not the RunPod reservation. There is no automatic provider capacity
provisioning or enabled serving autoscaler in this contract.

The host agent claims exact GPU UUIDs and enforces CPU/memory limits. Distinct-host
placement is model-specific. Insufficient resources leave pods Pending; keep
spare capacity for serving replacement. Readiness requires SDK qualification of
the exact process incarnation. Argo promotes qualified replacements while old
replicas retain an eleven-minute request drain.

The GPU reaches only the private control listener over Tailscale. It receives
no Kubernetes, database, Temporal or AWS administrative credentials. The EKS
controller uses Kubernetes RBAC and a host-specific root management key. Artifact
transfers use short-lived grants. Host and controller restarts preserve running
model processes; provider failure requires replacement capacity.

See [instance setup](INSTANCE_SETUP_PLAN.md),
[RunPod execution](../tools/virtual-kubelet/README.md), and
[Tailscale policy](../infra/modules/tailscale/README.md) for operational details.
