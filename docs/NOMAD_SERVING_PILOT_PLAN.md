# Nomad serving pilot

Status: draft for review. No infrastructure or serving changes are authorized by this document.
Updated: 2026-09-14.

## Objective

Move process placement, restart, and rollout management from manual commands to
Nomad. Start with one DeepSeek V4.1 Flash TP4 replica on one existing 4xB300
Runpod pod. Keep provider provisioning manual. Do not add training, adapters,
autoscaling, preemption, or automatic pod provisioning in this phase.

The hosts are Runpod Pods (containers with SSH), not full VMs. The user has
already run Nomad successfully on Runpod. That was a disposable experiment.
Build and qualify a reproducible client setup; no previous configuration is required.

The user confirmed that this pilot is not yet a production service. Downtime is
acceptable. Prefer a simple stop-and-start migration over temporary extra capacity
or a zero-downtime rollout. This does not authorize deleting pods or their data.
Select and verify the task driver and GPU assignment method before finalizing job specifications;
do not replace it with an assumed Docker-host architecture.

### Nested container check, 2026-09-14

Measured on Runpod pod `uv33dai39yeqe1`, using
`runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`, with four NVIDIA B300
SXM6 AC GPUs. Two TP2 vLLM workloads were running. The checks did not stop or
change those workloads. No additional pod was rented.

- Docker and dockerd were absent. `/var/run/docker.sock` was absent.
- `unshare --mount true`, `unshare --pid --fork true`, and
  `unshare --net true` each failed with `Operation not permitted`.
- `unshare --user --map-root-user true` failed with `Operation not permitted`
  both as root and through `runuser -u nobody --`.
- Effective and bounding capabilities were `00000000a80425fb`. Seccomp mode
  was 2. The cgroup v2 mount reported writable access; this did not permit
  namespace creation.

Inference: this pod cannot run standard nested Docker containers under its
current permissions. Rootless Docker also requires user namespaces. No Docker
daemon was installed or started after these prerequisite failures. This result
does not establish the capabilities of other Runpod configurations or providers.

The user then selected a stable provider base with separately versioned
runtime bundles, as recorded below. The job reserves GPUs and launches a
pinned bundle through `raw_exec`.

### Runtime bundle experiment

The user approved testing a stable provider base with separately versioned
runtime bundles and a separate model cache. First test runtime relocation on
the existing pod before selecting a bundle format for releases.

- Hypothesis: the existing self-contained vLLM environment can run from an
  extracted archive at a different path on the same provider base.
- Input: `/opt/glm53-stock-vllm-0.29.0` on `uv33dai39yeqe1`. Record the imported
  package versions; the directory name is not a version authority.
- Gate: verify the archive checksum, import vLLM and PyTorch from the extracted
  environment, run one single-element CUDA operation on each GPU, and load
  the vLLM CLI help. Do not load model weights or start a serving replica.
- Budget: no new rental, 600-second timeout, 15-second kill grace. Require
  space for two environment copies plus 4 GiB. Remove temporary files on exit.
- Harness: `product/inference/nomad/tests/probe-runtime-bundle.sh`. Run it
  inside the provider container through `timeout --kill-after=15s 600s bash`.
- Scope limit: this checks relocation on the same base. It does not prove
  base-image portability, DeepSeek compatibility, model-load time, or Nomad
  GPU worker cleanup. The system Python, driver, and system libraries remain
  dependencies of the bundle.

Measured result (2026-09-15, 03:09:41–03:10:36 UTC): all gates passed in
approximately 55 seconds on the existing pod. The source environment used
7.9 GiB. The imported versions were vLLM `0.28.1rc1.dev580+g385dce36b`,
PyTorch `2.13.0+cu130`, and CUDA `13.0`. The archive SHA-256 was
`9393930ce088e386b79c301dfffd5678abc6984a39b908e2305f419df97d3e23`.
This hash identifies the test archive, not a published release. Archive
verification and extraction took approximately 40 seconds together. No network
download or model load was measured. The CLI help check hid GPUs and reported
that it used `/usr/local/cuda` as CUDA_HOME.

Cleanup completed. No experiment directory remained. The same four existing
vLLM worker PIDs remained, with their original reported GPU memory usage.
Next: package a pinned runtime from a controlled build, declare its base
dependencies, and test Nomad startup and worker cleanup before a model swap.

### In-place Runpod image update, 2026-09-15

Measured on `uv33dai39yeqe1`: a PATCH of only `imageName` replaced the base
image without a Stop, Terminate, or Create request. The old image was
`runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`. The new image was
`runpod/pytorch@sha256:60baa36d3fb6b98fd4f4ece6b96776c83c01a8b7c540e54460ab4d496816141f`
(tag `1.0.3-cu1281-torch291-ubuntu2404`).

The machine ID remained `rnnuez505hyy`. All four GPU UUIDs matched before
and after. The container filesystem was replaced; `/workspace` survived.
The public SSH port changed from `39600` to `39555`. Rediscover connection
ports after base updates. This test supports in-place base updates on this
pod; it is not a provider-wide availability guarantee.

At the user's request, the full-filesystem backup was cancelled and its
partial archive removed. Only the 7.9 GiB serving environment and startup
hook were archived, producing a verified 4.18 GB compressed archive under
`/workspace/gradiated-image-update-backup-20260915`. Other local tools and
caches were intentionally not preserved. Model weights and launch settings
were already in persistent storage.

The serving environment was restored on the new base. The base's Jupyter
process occupied port 8888; it was stopped so the model proxy could bind.
Both GLM TP2 replicas passed health checks at 03:51:39 UTC and later passed
small synthetic chat-completion requests. The restore is verified.

### Runtime implementation

The current bundle contract and test commands are in
`product/inference/runtime-launcher/README.md`. Nomad owns download,
checksum verification, and extraction. The C++ launcher only checks the base
and supervises the entrypoint. The candidate DeepSeek job is not submitted.
The latest qualification results and remaining gates are recorded below.

## Initial placement

Scope revised by the user: one DeepSeek V4.1 Flash replica, TP4, on one four-B300
Runpod pod. This supersedes the initial three-pod, four-replica migration.
Keep the three Nomad servers in EKS. GPU fleet size does not set quorum size.
Select the target from the existing DeepSeek pods after checking their live state.
Do not stop, migrate, or delete other deployments as part of this first rollout.

| GPU pod | Allocation | GPUs |
| --- | --- | --- |
| One enrolled Runpod pod | DeepSeek V4.1 Flash, one TP4 replica | All four B300 GPUs |

No tensor-parallel traffic crosses pods. Capture CPU, RAM, disk, shared-memory,
GPU topology, and model-cache requirements from the working runtime. The GPU
count is a user requirement; verify actual runtime fit before cutover.

A process or health-check failure should trigger bounded local recovery. Loss of
the pod stops serving: there is no spare host or replica. Nomad cannot restore
capacity until a compatible replacement is enrolled. Downtime is accepted.

Use per-instance inventory, pinned per-model images, and reusable job configuration
from the start. Adding nodes must not require a new scheduler or provider-specific
model code. Later GLM TP2 packing and additional DeepSeek replicas remain planned
expansion, not acceptance criteria for this rollout. Provider provisioning and
replica-count changes remain manual; no autoscaler is needed yet.

## Ownership

The [parent plan](TASK_FINE_TUNING_FROM_TRACES_PLAN.md#2-services) already places
Nomad servers in EKS. This pilot uses that architecture: Argo manages the server
workload, and external GPU hosts run Nomad clients.

| Owner | Responsibility |
| --- | --- |
| Operator | Provision and replace Runpod pods; approve production cutover |
| Terraform | AWS infrastructure, network configuration, and prerequisites |
| Argo CD | Nomad server StatefulSet, services, and configuration in EKS |
| Git | Pinned runtime configuration, job definitions, health and rollout policies |
| Nomad | Placement, allocation lifecycle, process recovery, and rollout |
| Existing product catalog | Exact model and deployment identity |
| Existing status path | Runtime readiness and pressure reports to the control API |
| Gateway | Route to ready deployments through the existing routing state |

Do not introduce a second model catalog, custom scheduler, or request-path Nomad
lookup. Keep deployed model IDs, tokenizer, chat template, quantization, and
context limits unchanged during the management migration.

## Security contract

Status: agreed design. Controls below are release requirements, not claims about
current deployment. The pilot serves our pinned runtime code and exact base models.
Later fine-tuning uses LoRAs that we create. Arbitrary customer code is outside scope.
Customer-uploaded adapters remain a later feature.

### Network and identity

Three Nomad servers run in EKS. GPU pods run Nomad clients and vLLM. No Nomad
server runs on a GPU pod in the deployed architecture. The earlier colocated
server/client probe was a temporary qualification test.

GPU hosts connect directly to three public Nomad RPC endpoints with mutual TLS.
Each endpoint forwards TCP to one server ordinal. Keep the management HTTP API
and server gossip private. No SSH relay or fixed provider IP range is required.
Test all three endpoints, server discovery, and reconnect behavior before cutover.

| Credential | Scope and authority |
| --- | --- |
| Instance Nomad TLS certificate and private key | One host's credential, signed by the shared private CA; authenticate the Nomad client role and region |
| Runtime registration identity | Bind an approved instance, actual allocation, engine boot, endpoint, and release |
| Customer Gradiated API key | Authorize customer inference through the gateway; not issued to hosts for enrollment |
| Future scoped internal token | Authorize specific training or evaluation calls under RUN-04; outside the pilot |

Issue different credentials for each provider pod or machine, not for each GPU
or provider. Record provider membership in the instance inventory. Use one private
X.509 CA initially. Keep its signing key off GPU hosts and images.

A certificate proves possession of its private key. A copied public certificate
alone cannot impersonate a host. A stolen private key can. Unique certificates
do not by themselves enforce per-instance authorization: Nomad TLS checks role
and region. Enrollment, node identity, ACLs, and allocation validation must enforce
the remaining boundaries. No host receives a Nomad management token, EKS credentials,
CA signing authority, or broad AWS credentials.

A host certificate does not authorize customer inference through the gateway.
The host-to-control-API path and gateway-to-runtime path require their own explicit
authorization. An outbound RPC connection does not create a return inference route.
Keep vLLM on loopback or a restricted private interface. Before cutover, verify
that anonymous public requests cannot reach inference or administrative handlers.

### Process and secret separation

Run the Nomad client under a dedicated host-agent identity. Run vLLM
under a different OS user. Restrict host private-key files and directories to the
host agent. Do not place keys in model images, shared model caches, or the vLLM
environment. Apply the same isolation to status credentials that carry host authority.

The tested Runpod container can run a non-root process. However, raw_exec normally
runs a task as the Nomad agent user. The CPU probe does not prove key isolation.
Qualify a controlled launch mechanism for the separate vLLM user, GPU access,
termination, and cleanup. Do not grant arbitrary privilege escalation or a generic
root command interface to achieve this separation.

Root and the provider host remain trusted. Separate users protect against a
runtime-user compromise; they do not protect against root, a kernel escape, or
a compromised provider host. This pilot is not an isolation boundary for executing
untrusted customer programs.

### Renewal and revocation

Automate certificate renewal with a finite lifetime. Set and test lifetime,
renewal margin, and outage behavior before deployment. Renewal requires current
credential authorization. Do not let possession of an old credential renew
access after revocation.

Disabling a host must block renewal and runtime registration and remove its serving
routes. Reject late status that would reopen a removed route. Direct mutual TLS
has no immediate per-instance revocation mechanism in this design. Certificate
expiry does not close existing connections. If immediate RPC denial is required,
replace CA trust and reconnect healthy clients. This can affect fleet availability.
Test and measure that response before cutover. Removing access does not prove that
compute on the remote host stopped. Re-enroll only after host cleanup or replacement.

### Remaining risks

- Host or provider compromise can expose that host's keys, requests, and model data.
- Stolen host credentials can impersonate an enrolled client. Measure the permitted
  actions; do not assume the effect is limited to one instance by certificate naming.
- Compromised runtime code or dependencies can read requests and change responses
  even when the process cannot read host credentials.
- Authentication does not prevent all resource exhaustion. Bound connections,
  requests, timeouts, and model loading. Monitor RPC and control-plane failures.
- Revocation can fail if existing sessions or stale routes remain active.
- The single serving pod is a failure domain. Security isolation does not provide replica availability.

### Security release gates

1. From the vLLM user, prove that host-agent private keys and privileged tokens cannot
   be read through files, process interfaces, or inherited environment variables.
2. Prove that a host cannot submit arbitrary jobs, register another instance's
   allocation, obtain broad cloud credentials, or access private EKS services.
3. Test expired, untrusted, wrong-role, and wrong-region certificates. Test stale
   enrollment and allocation bindings. No failed check may create a serving route.
4. Disable one instance during active connections. Verify access denial, route removal,
   renewal denial, and rejection of late status within the declared bound.
5. Prove that anonymous callers cannot reach the model or administrative endpoints.
6. Verify reconnect and renewal through a provider IP change without broadening access.

Record results before calling the migration ready. The CPU restart probe is not
proof that these security gates pass.

### Later customer LoRA uploads

Use the existing [artifact acceptance contract](TASK_FINE_TUNING_SERVING_CONTRACT.md#art-01-accepting-an-artifact).
If customer uploads are added, accept data-only tensors and a closed configuration
schema. Reject pickle, executable model code, and custom import or loading hooks.
Validate tensor names, shapes, dtypes, finite values, rank, sizes, and exact-base
compatibility in an isolated process with memory and time limits.

Write a new canonical LoRA artifact from the validated tensors. Hash and publish
that approved copy; serving must not load the original upload. Parsing and conversion
remain attack surfaces, so rebuilding is an extra control, not proof of safety.
Artifact validation does not establish output quality or safe model behavior.
No upload route or customer-code execution is added in this pilot.

## Decisions still needed

The user confirmed a three-server quorum in EKS, managed by Argo CD. The
Runpod experiment does not need to be recovered. Qualify the client setup here.

Resolve these details through repository and host inspection:

1. Select the client driver, supervisor, persistent data directory, and GPU
   assignment method. Pin versions after qualification.
2. Identify the target DeepSeek pod and its current workload. Downtime is accepted,
   but preserve their data and saved launch commands.
3. Capture current vLLM versions, model revisions, ports, endpoints, and limits.
   Preserve working model-specific flags.

## Shared foundation from the fine-tuning plans

Build the inventory and enrollment part of FLEET-05 now. The parent plan lists
these under the private-model increment, but serving already needs them.
Training, adapter loading, run tokens, and autoscaling remain later work.

The deployed PostgreSQL schema has `model_deployments`, with provider, region,
fault domain, endpoint, and release fields. It has no `instances` table. Extend
the existing control package; do not create another inventory service.

### Instance record

One instance represents one provider machine or pod, not one serving replica.
The initial managed inventory has one instance and one serving deployment.

| Field group | Contents |
| --- | --- |
| Identity | Internal UUID, provider, provider account ID, provider instance ID |
| Location | Optional region and fault domain |
| Hardware | SKU, such as `4xb300` or `cpu-32vcpu` |
| Nomad link | Optional, unique Nomad node ID |
| Timestamps | Creation, update, and retirement times |

Provider, account, and provider instance ID form the unique provider identity.
A replacement provider pod receives a new instance record. Nomad owns device
inventory, scheduling eligibility, resource availability, and allocations.
Do not copy these fields into PostgreSQL. Credential issuance and revocation
remain separate from inventory. A retirement timestamp does not revoke access.

### Enrollment and serving registration

1. The operator records the instance and issues its scoped credentials.
2. The client authenticates. Verify its credential authorization separately
   from the inventory record.
3. Verify the client's Nomad node identity and bind it to the instance.
4. Each runtime registers its actual job, allocation, node, engine boot, exact
   release, and endpoint. The API validates these against Nomad and its identity.
5. Bind subsequent readiness reports to that registration. Reject status from
   an old allocation or engine boot.
6. To revoke access, revoke credentials and terminate active sessions. Stop
   affected workloads and remove their routes. A database change alone is not enough.

Add an optional instance reference to existing deployments for migration.
Manual deployments remain readable until moved. Do not create PostgreSQL
allocation history or a desired-placement table. Use the existing deployment
projection and Valkey routing path; the gateway does not query Nomad.

Git jobs must reference immutable catalog releases as FLEET-00 requires. The
current deployment release JSON needs an explicit migration to a stable release
identity before job rendering. Define that small catalog change with the
instance schema. Keep private adapters and training artifacts outside this change.

### Implementation order

1. Define and implement instances, enrollment, immutable release references,
   and operator commands in the existing control package.
2. Deploy three Nomad servers and qualify an external Runpod client.
3. Add authenticated runtime registration and stale-status rejection.
4. Add the pinned DeepSeek vLLM job and move the selected pod.
5. Verify recovery, drain, rollback, and inventory replacement.

Update the canonical data model when implementing these records. Tests must cover
duplicate provider identities and node bindings. Authentication tests must cover
revoked credentials, wrong allocation ownership, and late status after replacement.

## Work packages

### 1. Inventory and qualify the client setup

- Record the selected pod ID, its four GPU UUIDs, interconnect topology, CPU/RAM,
  persistent volumes, current processes, and endpoint mappings. Do not record secrets.
- Select a driver that works inside the actual Runpod container. First qualify
  a harmless task, then GPU assignment and process-tree cleanup.
- Verify the client survives its supervisor restart, reconnects to the server, and
  preserves allocation identity. A new pod must not reuse a stale node identity.
- Pin Nomad, the task/device plugins in use, vLLM, and model artifacts.
- Capture the manual start/stop procedure for each replica as the rollback path.

Exit: a reproducible client setup and a complete inventory. No live workload moved.

### 2. Establish the control plane and connectivity

- Deploy the three-replica Nomad server StatefulSet in EKS through Argo CD, with persistent state,
  snapshots, and a restore procedure. GPU clients remain external to EKS on Runpod
  and, later, other providers. They join Nomad, not Kubernetes.
- Configure ACLs and encrypted authenticated server/client communication. Keep the
  management API private or behind an authenticated operator path.
- Verify reachability through the actual Runpod network and NAT. Do not assume pod IPs
  or forwarded ports remain stable after recreation.
- Establish distinct operator and deployment credentials. Deliver secrets outside Git.
- Verify GPU workloads continue during a brief server interruption and reconcile once
  connectivity returns. Do not replace disconnected allocations while the old process
  may still be serving without an endpoint-fencing policy.

Exit: clients connect reliably; control-plane restart and credential boundaries pass.

### 3. Define serving jobs and GPU ownership

Initial job, subject to driver qualification:

- One DeepSeek service job with count 1 and a TP4 runtime.
- Constrain placement to approved instances with the qualified runtime and four B300 GPUs.
- Reserve the complete GPU inventory for this first workload. Keep CPU/RAM and
  ports explicit. Do not allow a manual process to retain assigned GPUs.
- Verify visible GPU UUIDs and worker processes. An environment-variable mask alone
  is not proof of device ownership.
- Keep replica count and runtime configuration in Git. Additional nodes use the
  same enrollment flow. Do not name a specific provider pod in normal job policy.

If the driver uses process tasks with fixed GPU masks, record that limitation.
One allocation per four-GPU host is sufficient for this rollout. Dynamic partial-GPU
allocation and two GLM TP2 allocations on one host require later qualification.

Exit: rendered jobs demonstrate the intended placement and resource ownership.

### 4. Preserve serving endpoints and readiness

Reuse the current vLLM status reporter and authenticated proxy where practical:
`product/inference/runtimes/vllm/report_status.py` and
`runpod-auth-proxy.nginx.conf.template`. The proxy currently exposes two GLM routes;
confirm the actual deployed configuration before reusing it for DeepSeek.

- Map each allocation to exactly one deployment identity and endpoint.
- Gate readiness on completed model load, exact model identity, and a small valid
  request. Process existence or an open port is not sufficient.
- Keep startup allowance separate from runtime liveness. Measure load time before
  choosing failure thresholds, so slow model loading does not cause a restart loop.
- Keep streaming, authentication, timeouts, and pressure reporting intact.
- Before shutdown, withdraw readiness, allow routing state to converge, and drain
  active requests. Stop all worker processes before reusing their GPUs.
- Keep runtime and reporter lifecycle tied together; stale readiness must expire.

Exit: the gateway sees the same exact models and routes only to ready allocations.

### 5. Move each pod to Nomad management

Downtime is acceptable. Move one pod at a time to keep diagnosis simple; there is
no minimum ready-replica requirement during this migration.

1. Save the current commands, configuration, endpoint mappings, and model-cache paths.
2. Withdraw the pod's manual replicas from routing and stop their process trees.
3. Verify that GPU memory and ports are released. Keep model files and pod storage.
4. Start the Nomad-managed workload using the same runtime and model configuration.
5. Check model identity, a streamed request, readiness, and GPU ownership.
6. Restore routing and confirm requests reach the intended replicas.
7. Verify exactly one ready Nomad-managed DeepSeek replica on the selected pod.

If a gate fails, stop the Nomad workload, verify cleanup, and restart the saved manual
configuration. Restore routing only after readiness passes.

No extra GPU canary or temporary pod is needed. Test graceful drain and replacement
after the initial migration. Updates can cause downtime with this one-replica layout.

### 6. Qualify recovery and handoff

Test in increasing order of impact:

- Kill one serving process; verify bounded restart, no duplicate workers, and readiness.
- Restart its Nomad client supervisor; verify recovery without a duplicate allocation.
- Interrupt control-plane connectivity; verify running inference and safe reconciliation.
- Trigger a failed model startup; verify no routing and a working rollback.
- Test a planned replica replacement and graceful drain with a long streamed request.
- Test pod loss only with explicit operational approval. Expect the documented capacity
  shortfall; do not evict another model to conceal it.

Monitor desired, allocated, and ready replicas separately, plus restarts, pending
allocations, GPU ownership, request failures, and model-load time. Set numerical
latency/error gates and observation periods from a recorded baseline before cutover.

## Deliverables

Use `product/inference/nomad/` for job templates, rendered non-secret examples,
client bootstrap, qualification checks, and the operating runbook. Use `infra/` for
control-plane infrastructure. Keep runtime-specific wrappers under
`product/inference/runtimes/vllm/`.

The runbook must cover enrollment, deploy, drain, rollback, pod replacement, server
restore, secret rotation, and checking the single expected DeepSeek replica. Record results
and accepted driver limitations before calling the pilot complete.

## References

- [Fleet ownership and scheduling](TASK_FINE_TUNING_FLEET_CONTRACT.md)
- [Runpod Pods](https://docs.runpod.io/pods/overview)
- [Nomad GPU device resources](https://developer.hashicorp.com/nomad/docs/job-specification/device)
- [Nomad NVIDIA plugin](https://developer.hashicorp.com/nomad/plugins/devices/nvidia)
- [Nomad raw-exec driver](https://developer.hashicorp.com/nomad/docs/deploy/task-driver/raw_exec)

Provider documentation informs qualification. It does not override the user's
reported Nomad result; the pilot must establish its own reproducible setup.

## Implementation progress — 2026-09-14

Merged origin/main at f95f36fb, including PR #46. DeepSeek now has a recorded
V4.1 image digest, model revision, TP4 launch script, and two target pod IDs.
Its README still marks production registration as pending; check live state.

Added model-specific image packaging under product/inference/images. DeepSeek
uses its recorded digest. GLM requires packaging the existing runtime into a
pinned image. Neither new image has passed a build or GPU qualification yet.
Runpod bootstrap remains separate. Do not assume nested Docker support.

Added the instances schema, optional deployment reference, and migration. The
control service registers inventory and sets or clears the Nomad node link.
The schema uses a hardware SKU and does not store device inventory, eligibility,
or enrollment state. The authenticated enrollment endpoint and Nomad node
verification remain pending. Database integration tests cover GPU and CPU SKUs,
provider identity uniqueness, and unique node links. No local or production
application database was migrated.

AWS access and pod SSH access were established. GLM source changes were captured.
The non-root Nomad 2.0.6 CPU recovery probe passed in 4.02 seconds. Separate-user
launch, GPU isolation, and the security gates above remain unqualified.

Next: implement and qualify direct mutual TLS and per-instance identities, build
the DeepSeek image, and implement authenticated enrollment and runtime registration.
Then deploy the three-server control plane and the single DeepSeek job. GLM image
work is retained for later expansion and does not block this rollout.

### Component naming and host language

GPU hosts run the Nomad client. Custom GPU host-agent code uses C++.
The selected vLLM runtime remains unchanged. No custom transport service is needed.

### Test locations

Model launch tests stay in `product/inference/images/tests`. Nomad server
configuration tests stay in `infra/environments/prod/us-east-1/kubernetes/nomad/tests`.

The one-off Runpod CPU probe and raw results moved to the ignored local folder
`.agents/runtime/nomad-qualification`. They are not production code or a required
test suite. The durable result is the 4.02-second synthetic recovery recorded
above. The harness attempted cleanup; a later external SSH cleanup check could
not complete. Do not treat this probe as proof of complete process cleanup.

Model launch and Nomad configuration checks use shell and run in CI.

### Remote sync and relay workload — 2026-09-14

Merged remote main at `411ad9da`. Its production record now reports both
DeepSeek replicas active. Recheck that state before any migration; the earlier
assumption that the selected pod is not serving production is no longer valid.

Historical design, superseded by direct mutual TLS below: prepared three SSH relay pods on separate nodes, an internal Service, and a
disruption budget with `minAvailable: 2`. The
manifest requires a published image digest and external key/config provisioning.
No public endpoint or Argo application was added. No cluster change was applied.

### Image publication workflows

`build-images.yml` resolves immutable digests for each caller's required images.
Application, Nomad, and model deployment workflows are independent. The application
sequence retains its production rollout. Nomad validates manifests and uses the pinned upstream image;
model publication stops before GPU qualification or rollout. The input catalog
and checks are documented in `tools/images/README.md`. GLM publication remains
disabled until a qualified base image digest is recorded.

### Direct RPC decision — 2026-09-14

The user selected direct mutual TLS instead of the SSH relay. Remove the relay
service, client tunnels, host key, access inventory, and custom image workflow.
Use one public TCP NLB per Nomad server. HTTP and gossip remain private.

A compromised provider or pod can steal its Nomad client credentials. The relay
would not contain the resulting hostile Nomad traffic. This design accepts that
trust boundary for our workloads. It does not claim isolation between providers.
The release gates above still require credential, allocation, and runtime checks.

### Live driver qualification and capacity, 2026-09-15

The approved EC2 quota is 16 vCPUs. Retrying the existing desired capacity of
six brought two additional m7i.large nodes online. All six nodes were Ready,
with two nodes per availability zone. Restore the server CPU request to
500m; retain the existing memory reservation, limits, and quorum PDB.

Both GLM health endpoints passed at 03:51:39 UTC after the base-image update.
The later live Nomad probe used no model weights or GPU memory. It ran a
temporary, loopback-only server and client, not a connection to EKS.

Measured with Nomad 2.0.6 and NVIDIA device plugin 1.1.0 on the Runpod pod:

- GPU inventory found all four B300 devices.
- Two raw-exec allocations requesting two GPUs received disjoint UUID pairs.
- Stopping the job removed its ordinary child processes.
- The first test left two detached children alive. The supervisor correction
  below resolved this synthetic failure. GPU visibility masks do not provide isolation.
- The harness removed the remaining processes and its temporary account.

Reproduction: `product/inference/nomad/tests/qualify-raw-exec.sh`, run under
a 240-second timeout as root in the selected pod. The harness creates a
temporary unprivileged account, binds loopback ports 24646–24648, and removes
its files and processes on exit. Do not run it against a production Nomad
agent. Existing workloads remain outside the test scheduler's inventory.

Production capacity rollout completed: all six EKS nodes and all three Nomad
servers are Ready. Each server requests 500m CPU and 1 GiB memory. Autopilot
reports all three voters healthy with failure tolerance 1. Anonymous operator
access remains denied. Argo applied the approved resource change from the
branch revision. Its parent configuration restored the source to `main`, so
the application is Healthy but OutOfSync until PR #55 is merged. Do not sync
the older main revision, which would restore the temporary 100m requests. No external RPC load balancer was created, and no GPU
client is enrolled with the EKS quorum yet.

Both restored GLM replicas also passed a small synthetic chat-completion
request. The earlier base-image restore is verified.

### Process cleanup correction, 2026-09-15

The C++ launcher now supervises its runtime with Linux child-subreaper mode.
It adopts orphaned descendants even when they start a new session. On runtime
exit or a shutdown signal, it requests termination, escalates after 25 seconds,
and reaps all descendants before returning. It preserves the main runtime's
exit status. Nomad's task kill timeout remains 60 seconds.

Local tests passed for normal shutdown, normal runtime exit, runtime crash,
double-forked descendants, and descendants that ignore SIGTERM. An unrelated
process stayed alive. The first live run lost its final result over SSH and
is not counted as a pass. The rerun used a non-blocking job-stop API request
and SSH keepalives. It passed two disjoint GPU assignments and reported
`cleanup_survivors=0` before the harness removed its account and files.

This resolves the earlier synthetic detached-process cleanup failure. It
does not prove real vLLM worker recovery or cleanup after SIGKILL of the
supervisor itself. Runtime-user separation and a real model stop/restart test
remain deployment gates. The live test used the same supervisor source through
a small test adapter; it did not replace either running GLM service.

### Runtime bundle simplification

The current job uses Nomad's native artifact block for archive download,
SHA-256 verification, and extraction. The launcher now only checks the base ID
and entrypoint, sets the runtime directory, and supervises worker cleanup.
Removed libcurl, OpenSSL, libarchive, digest locks, and the shared runtime cache.
Runtime bundles now belong to each allocation. Model weights keep their
persistent cache. Release submission must provide runtime disk capacity.

The client example sets a 10-minute download timeout, 20-GiB download limit,
40-GiB extraction limit, and 200,000-file limit. Keep artifact inspection
enabled. These bounds need checking against the first published bundle.

Measured locally: the existing detached-process fixture leaves a worker alive
under Tini 0.19.0 with `-s -g`. Keep the small C++ supervisor. The simplified
launcher passes the base-ID, entrypoint, argument, stop, exit, crash, and
SIGTERM-resistant descendant tests. A local Nomad 2.0.6 fixture also passed
HTTPS download, checksum verification, extraction, entrypoint launch, and
wrong-checksum rejection. Job and client configuration validation passed.
This change does not qualify a real vLLM restart or deploy a GPU client.
