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

## H200 TP2 alongside B300

H200 GLM capacity is a separate `glm-dealign-sglang-h200` Rollout for the same
public uncensored model, alongside the existing B300 Rollouts. It has a distinct
runtime profile, H200 node selector and an explicit instance allowlist. The
existing B300 runtime pins, placement, replica counts and fleet image pin do not
need to change. Do not label H200 nodes as B300 or reuse the 400 GiB B300 request.
The candidate launch settings and their unmeasured limits are in the
[runtime README](../product/inference/runtimes/glm-sglang/README.md#h200-tp2-profile).

1. Merge the preparation changes and let the product deployment install the
   expanded ops-MCP enrollment contract and the GPU platform's H200 CRD enum.
   Model deployment publishes a new `glm-5-3-flash-sglang` archive whose release
   record lists `h200-tp2` in `runtimeProfiles`. Publishing it does not select it
   for any existing B300 Rollout. Retain the current fleet image pin: a new base
   image is not required on the already-rented H200 pods.
2. Each new pod needs its own fresh single-use `tag:gpu-bootstrap` key. First
   verify it is online as `gpu-bootstrap-<pod ID>`. A reused or expired key can
   leave the container running without a usable tailnet identity. Recover that
   bootstrap login inside the running pod; changing its provider environment,
   image or ports resets it and can lose the reservation. Never paste keys into
   chat or Git. If there is no working shell, obtain explicit authorization
   before using registration's provider-reset option.
3. Pods rented with the older pinned base image have an enrollment module that
   recognizes only B300 and RTX PRO 6000. Once the bootstrap identity is online,
   an administrator can prepare it from a merged commit without a provider
   reset. Fetch `origin/main`, use the full merged SHA containing H200 support,
   review the dry run, then apply:

   ```sh
   git fetch origin main
   python3 tools/gpu/prepare-enrollment.py --gpu H200 --pod s0j3lwoqorm674 --source "$MERGED_SOURCE_SHA"
   python3 tools/gpu/prepare-enrollment.py --gpu H200 --pod s0j3lwoqorm674 --source "$MERGED_SOURCE_SHA" --apply
   ```

   The helper uses administrator Tailscale SSH, including its normal MFA
   checkpoint. It requires the matching bootstrap identity, exactly two idle
   H200 GPUs and no existing enrollment. It atomically updates only `enroll.py`
   and the result schema, retaining `.before-h200` backups. It does not restart
   processes or touch provider settings. A newly built image already contains
   these files. To undo preparation before enrollment, restore those two backups
   over the same administrator SSH path. After enrollment, leave the host's
   software intact and roll back model placement instead.
4. Use the private `register_instance` path above with `reset_running_pod: false`.
   Commit each returned measured `GpuHost`, render its permissions and secret
   projection, and verify the Node is Ready. Do not invent instance UUIDs,
   memory budgets or management-secret references from the provider pod ID.
5. Download the published SGLang `release.json`. Its source must include the H200
   profile; an existing B300-only archive is rejected. Stage one H200 replica
   using the registered instance UUIDs, initially choosing only the first host:

   ```sh
   python3 tools/gpu/stage-glm-pool.py --gpu h200 "$RELEASE_JSON" "$BUNDLE_SOURCE_SHA" --instances "$H200_INSTANCE_UUID"
   python3 tools/gpu/stage-glm-pool.py --gpu h200 "$RELEASE_JSON" "$BUNDLE_SOURCE_SHA" --instances "$H200_INSTANCE_UUID" --write
   python3 tools/gpu/render-config.py
   node tools/models/model-replica-rules.mjs
   ```

   Review and merge the generated runtime catalogue, model catalogue, H200
   Rollout, controller ConfigMap, model ApplicationSet and replica-alert rules.
   The helper validates committed RunPod H200 inventory with two GPUs, at least
   32 CPU and 320 GiB of allocatable RAM. It creates one replica with no surge,
   an HPA cap of one, and `serving_mode: qualification`. The separate private
   runtime model ID keeps that pool out of public routing. B300 definitions are
   preserved, including other canaries for the same public model.
6. On H200, require cold-cache model load and warmup, no kernel/Marlin/FlashMLA
   errors, SDK qualification of the exact process incarnation, streaming and
   tools, reasoning, prefix-cache reuse, mixed and long prompts, cancellation,
   queue-full/expiry behavior, concurrency four and normal drain. Record GPU
   memory and pool capacities, TTFT and decode rate. CPU tests and successful
   manifest rendering do not satisfy this gate. Inspect model loads that die
   before readiness; do not bypass warmup or SDK analysis to admit them.
7. After those checks pass, rerun the same staging command with `--promote --write`,
   render both manifests and alert rules again, and review the production-mode
   change. Promotion requires the exact previously staged model and runtime.
   It maps qualified H200 endpoints to the existing public model, so the gateway
   can route across both GPU pools. SDK analysis still applies, and the rollout
   proceeds to full weight automatically once it passes; never use full
   promotion to skip it. Observe the initial exposure for at least 20 minutes
   before expanding.

To stage all three hosts for isolated qualification, supply all three registered
UUIDs to `--instances` and `--replicas 3` on the initial staging call; otherwise
leave replicas at one. Later changes to the allowlist, replica/HPA caps, runtime
or resources require an explicit reviewed catalogue edit and regeneration: the
helper refuses to overwrite a different existing deployment. Recheck capacity
and qualify each new process. Keep both GPU pools until routed H200 availability
and performance are measured; H200 capacity does not justify retiring B300s.

Rollback H200 public exposure by changing only its `serving_mode` to
`qualification` and regenerating. To stop the H200 workload, set only its
`autoscaling.paused_replicas` to `0`, render, and wait for the normal request drain.
Keep its manifests, immutable runtime, enrolled hosts and provider reservations
for inspection and retry. A new runtime can be staged as another isolated
revision through an explicit reviewed edit. Neither rollback nor qualification
should reset or terminate a RunPod pod.

## B200 alongside B300

B200 GLM capacity is a separate `glm-dealign-sglang-b200` Rollout for the same
public uncensored model, staged and promoted exactly like the H200 pool above
with `--gpu B200` for enrollment preparation and `--gpu b200` for staging. B200
is Blackwell, so its `b200-pcp2` profile keeps the B300 launch settings and
halves the admission limit to eight requests for its smaller HBM. It requests
320 GiB of host RAM and never changes B300 pins, placement or replica counts.
Record the measured pool capacity before raising that limit.

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

Model rollouts have no pause step: each proceeds to full weight once its SDK
analysis passes. Use Argo Rollouts to inspect, pause and abort one. The model
ApplicationSet preserves `/spec/paused`, so Argo CD self-healing does not undo an
operator pause. Resume a manual pause by clearing only `spec.paused`. Do not use
`promote`: during analysis it advances past that analysis, and `--full` skips all
remaining analysis.
A pause controls revision progression and does not freeze the HPA's desired
replica count. A manually paused completed Rollout can nevertheless leave its
ReplicaSet below that desired count. For replica-count-only expansion, resume
within the reviewed HPA caps until the target pods are created, then pause again.
Verify actual pod readiness and SDK qualification before treating the desired
count as serving capacity. Keep the model configuration and scaling caps in Git.

```sh
kubectl argo rollouts get rollout glm-dealign-sglang -n gpu-inference
kubectl argo rollouts pause glm-dealign-sglang -n gpu-inference
kubectl patch rollout glm-dealign-sglang -n gpu-inference --type merge -p '{"spec":{"paused":false}}'
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

The SGLang migration keeps the combined footprint at twelve B300 GPUs. The
first serving trial used one two-GPU SGLang replica alongside ten one-GPU vLLM
replicas. Expand to three SGLang plus six vLLM, then four plus four. The first
expansion replaces the four co-located vLLM replicas on the four-B300 host;
the next expansion replaces one co-located pair on the eight-B300 host. The
four-plus-four stage gives SGLang roughly half of uniformly distributed routing
keys; prefix affinity and load can change the measured request share.
Keep each runtime's autoscaling maximum at its reviewed stage count. Hold each
stage until the operator explicitly authorizes further migration.

SGLang placement is restricted to the original two-B300 host, the four-B300 host
`01a0f19d-1ff3-7613-8cbf-81b693c0f0d4`, and the eight-B300 host
`01a0fbf7-5276-700b-903b-7e04da150ed6`. Two SGLang replicas fit the four-B300
host's 64 CPU and 896 GiB; one fits beside DeepSeek and two remaining vLLM
replicas on the eight-B300 host. Do not place a second 400 GiB SGLang allocation
beside the normal GLM allocation on its 686 GiB host, or use the excluded host.

After the four-plus-four trial, one further pair migration gives five SGLang
plus two vLLM replicas within the same twelve-GPU footprint. Replace the two
remaining vLLM allocations on the eight-B300 host with a second SGLang replica.
DeepSeek plus two SGLang replicas request 96 CPU, 1200 GiB and eight GPUs,
within that host's 171 CPU, 1389 GiB and eight-GPU allocatable capacity. Keep
both vLLM replicas beside normal GLM on its four-GPU host; another SGLang
allocation there would exceed the current memory requests. Cap SGLang at five
and vLLM at two, with disruption-budget minima of four and two respectively.
This gives SGLang roughly five sevenths of uniformly distributed routing keys;
observe actual request share and hold until the next explicit authorization.

After the five-plus-two trial, the final vLLM pair can be retired by setting
`glm-dealign.autoscaling.paused_replicas` to `0`, then running
`python3 tools/gpu/render-config.py` and
`node tools/models/model-replica-rules.mjs`. This sets both
the Rollout count and the KEDA pause to zero, preventing autoscaling from
restoring vLLM. Rendering also caps its disruption-budget minimum at the paused
replica count (zero when retired); removing the override restores the configured
two-pod budget. Keep the two-replica rollback configuration and leave SGLang
capped and manually paused at five replicas. Let accepted vLLM requests drain
normally; verify all five SGLang allocations remain qualified and public
gateway requests succeed. Removing the pause override restores the reviewed
two-replica vLLM configuration if rollback is needed; run both rendering
commands again and include the replica-rule changes in the rollback PR. With
vLLM retired, the production SGLang pool carries the five-replica alert floor;
restoring vLLM restores its baseline floor and the canary warmup semantics.

The B300 SGLang pool `glm-dealign-sglang` is one Rollout placed on any B300 host
except retired ones; the scheduler fills each host by its free GPU pairs. Its
runtime profile reuses the exact verified SGLang bundle and served release through
the catalogue's per-base `bundles` mapping, with a 256 GiB memory request and a
400 GiB hard limit, so two replicas fit a four-GPU B300 host (85 CPU, 686 GiB).
Check the provider cgroup memory limit and usage, not host-wide `/proc/meminfo`,
for headroom. The runtime profile ID is a scheduling identity; the archive
remains pinned to its separate SHA-256 in `bundles`. DeepSeek and stock GLM are
paused at zero, so B300 capacity serves only this pool. An earlier separate
`glm-dealign-sglang-sixth` Rollout pinned to `01a19221` existed only while stock
GLM shared that host.

Before each vLLM reduction, identify the qualified, co-located pods
by UID and set their `controller.kubernetes.io/pod-deletion-cost` annotation to
`-10000`, retaining the other pods' default cost. Require all current pods to be
Ready and the ReplicaSet identity unchanged immediately before the scale-down.
Deletion cost guides selection; it is not a hard placement guarantee. Observe
which UIDs terminate, wait for normal request drain and allocation release, and
verify the intended host capacity is free before proceeding. If a different
pod is selected or another replica fails, stop expansion and restore the previous
reviewed replica counts; do not force-delete requests or drain another pair.
Remove owned deletion-cost annotations from surviving pods when a stage ends.

The first expansion keeps six vLLM replicas serving throughout warmup. A
placement-template change can also restart the original SGLang replica. Before
syncing a placement change, manually pause SGLang until the new HPA bounds and
Rollout replica count are observed, then resume revision progression; Git does
not directly own the live replica count while the HPA is active.

A previous revision pinned to one two-GPU host may become Pending if the new
revision occupies that host. The rollout releases the old pending pod and
finishes the template migration once the new revision's SDK analysis passes. Verify every
resulting replica is SDK-qualified and test the new host allocations before
the later replica-count-only expansion.
Never use full promotion to skip analysis. 
Aborting SGLang does not recreate vLLM replicas removed from the other Rollout;
rollback must also restore the previous reviewed placement and replica counts.

To hold an initial exposure, pause the Rollout manually and observe routed
availability, runtime failures, TTFT, decode throughput and capacity rejections
for at least 20 minutes before resuming. Argo's replica weight is not an exact request
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
