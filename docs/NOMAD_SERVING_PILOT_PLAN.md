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

GPU hosts initiate authenticated outbound TCP tunnels to EKS. Forward only the
three private Nomad RPC destinations. Do not grant shell access, arbitrary port
forwarding, or general access to the EKS network. Keep the Nomad management API
and server gossip private. Fixed provider IPs are not required for identity or
reconnection. Source-IP restrictions may be an extra control where practical.
This replaces the earlier proposal to expose source-restricted Nomad RPC endpoints.

The proposed transport is SSH TCP forwarding. A local listener on the GPU pod
forwards bytes to a specific private server endpoint. It is not a Nomad server.
Test server address discovery, all three destinations, and reconnect behavior;
forwarding one bootstrap address is not sufficient.

| Credential | Scope and authority |
| --- | --- |
| Instance tunnel SSH key | One approved host; only its permitted forwarding destinations |
| Instance Nomad TLS certificate and private key | One host's credential, signed by the shared private CA; authenticate the Nomad client role and region |
| Runtime registration identity | Bind an approved instance, actual allocation, engine boot, endpoint, and release |
| Customer Gradiated API key | Authorize customer inference through the gateway; not issued to hosts for enrollment |
| Future scoped internal token | Authorize specific training or evaluation calls under RUN-04; outside the pilot |

Issue different credentials for each provider pod or machine, not for each GPU
or provider. Record provider membership in the instance inventory. Use one private
X.509 CA initially. The SSH key is a separate credential; the SSH tunnel does not
use the Nomad TLS certificate. Keep the CA signing key off GPU hosts and images.
Keep Nomad TLS enabled inside the tunnel.

A certificate proves possession of its private key. A copied public certificate
alone cannot impersonate a host. A stolen private key can. Unique certificates
do not by themselves enforce per-instance authorization: Nomad TLS checks role
and region. Enrollment, node identity, ACLs, and allocation validation must enforce
the remaining boundaries. No host receives a Nomad management token, EKS credentials,
CA signing authority, or broad AWS credentials.

A host certificate does not authorize customer inference through the gateway.
The host-to-control-API path and gateway-to-runtime path require their own explicit
authorization. An outbound RPC tunnel does not create a return inference route.
Keep vLLM on loopback or a restricted private interface. Before cutover, verify
that anonymous public requests cannot reach inference or administrative handlers.

### Process and secret separation

Run the Nomad client and tunnel under a dedicated host-agent identity. Run vLLM
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

Disabling a host must block new tunnel authentication and renewal, close its active
tunnel connections, reject new runtime registration, and remove its serving routes.
Reject late status that would reopen a removed route. Set and measure the maximum
revocation-to-denial time before cutover. Certificate expiry alone is not immediate
revocation. Removing access does not prove that compute on the remote host stopped.

Test that disabling one instance leaves other instances connected. Replace keys
and re-enroll only after cleanup or replacement of a compromised host.

### Remaining risks

- Host or provider compromise can expose that host's keys, requests, and model data.
- Stolen host credentials can impersonate an enrolled client. Measure the permitted
  actions; do not assume the effect is limited to one instance by certificate naming.
- Compromised runtime code or dependencies can read requests and change responses
  even when the process cannot read host credentials.
- Authentication does not prevent all resource exhaustion. Bound connections,
  requests, timeouts, and model loading. Monitor tunnel and control-plane failures.
- Revocation can fail if existing sessions or stale routes remain active.
- The single serving pod is a failure domain. Security isolation does not provide replica availability.

### Security release gates

1. From the vLLM user, prove that host-agent private keys and privileged tokens cannot
   be read through files, process interfaces, or inherited environment variables.
2. Prove that a host cannot submit arbitrary jobs, register another instance's
   allocation, obtain broad cloud credentials, or open undeclared tunnel destinations.
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

Next: implement and qualify the private tunnel and per-instance identities, build
the DeepSeek image, and implement authenticated enrollment and runtime registration.
Then deploy the three-server control plane and the single DeepSeek job. GLM image
work is retained for later expansion and does not block this rollout.

### Component naming and host language

The SSH relay runs in EKS and is separate from the inference gateway. Its
account reconciler uses Rust in `product/services/ssh-relay`. Custom GPU host-agent code uses C++.
GPU hosts also run the Nomad and OpenSSH clients. The earlier Python CPU probe
was a test fixture, not the production host agent. The selected vLLM serving
runtime remains unchanged.

### Test locations

Model launch tests stay in `product/inference/images/tests`. SSH relay tests
live in `product/services/ssh-relay/tests`. Nomad server configuration tests
live beside the Kubernetes configuration in
`infra/environments/prod/us-east-1/kubernetes/nomad/tests`.

The one-off Runpod CPU probe and raw results moved to the ignored local folder
`.agents/runtime/nomad-qualification`. They are not production code or a required
test suite. The durable result is the 4.02-second synthetic recovery recorded
above. The harness attempted cleanup; a later external SSH cleanup check could
not complete. Do not treat this probe as proof of complete process cleanup.

The regular relay unit tests use `cargo test`. Its Docker integration test also
uses Rust and runs explicitly with `--test tunnel -- --ignored`. Model launch
and Nomad configuration checks use shell, matching their launch scripts. Run
these checks when the related component changes. They are not yet wired into CI.
