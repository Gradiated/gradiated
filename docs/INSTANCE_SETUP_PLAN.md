# Instance registration and Nomad-managed model deployments

Status: agreed direction. Step 1, instance registration, is implemented. Builds on the
[Nomad serving pilot](NOMAD_SERVING_PILOT_PLAN.md), which this does not replace.

## Goal

Adding GPU capacity is one ops MCP call that puts only a trust bootstrap on the machine. Deploying a model is one merged file. Nobody
uploads runtimes to a host or writes service URLs by hand.

```
register_instance(provider, instance_id)        (ops MCP)
  → instance row + host credentials + Gradiated host image + Nomad node joined

merge product/inference/nomad/jobs/<model>.nomad.hcl
  → CI submits it → Nomad places replicas on eligible GPUs → each allocation
    registers itself and reports status → the gateway routes to it
```

## Instance registration

Registration runs inside the ops MCP (`product/services/ops-mcp/src/instances`), the
staff admin portal, as its only write tool. The provider selects an implementation
of one interface, so a second provider is a new implementation rather than a new
tool.

```ts
interface InstanceProvider {
  // Identify an existing machine and read what it is: account, SKU, location.
  describe(providerInstanceId: string): Promise<ProviderInstance>;
  // Whether a bootstrap can proceed without resetting a running machine.
  isStopped(providerInstanceId: string): Promise<boolean>;
  // Point it at the host image and hand it its bootstrap.
  bootstrap(instance: ProviderInstance, image: HostImage, environment: Record<string, string>,
            options?: { allowReset?: boolean }): Promise<void>;
}
```

Registration puts only the trust bootstrap on the machine, because that is the one
thing Nomad cannot deliver: it cannot give a node the credentials it needs to join
Nomad. Everything after that is Nomad's job. Registration:

1. Records the `instances` row from `describe`. Provider, account and instance id
   are the unique identity; registering the same machine again keeps its instance
   id, and a replacement machine is a new row.
2. Issues the instance's own Nomad client certificate, signed through KMS by the
   private CA, whose key never leaves KMS (ECDSA — the client rejects Ed25519). Credentials are per instance, never per GPU
   or per provider.
3. Reuses the node id and secret the machine already carries for this instance,
   so a renewed machine returns to Nomad as the same node, or generates new ones.
   It then calls `bootstrap`, which sets the
   machine's image to a pinned `nomad-base` and passes that node identity, certificate, key and the runtime bundle read key
   through the provider's own configuration. Nothing is uploaded and nothing is
   copied over SSH.
4. Waits for the node to report ready carrying this instance's id in its metadata,
   and only then binds `nomad_node_id` to it. A failed or re-run registration
   leaves the current binding in place.

`nomad-base`'s entrypoint writes that bootstrap into place, clears it from the
environment and starts the client on every boot. Nomad reads the node id and
secret from its data directory, so the node keeps the id recorded on the instance
across resets. For RunPod the bootstrap travels as pod environment, which matters:
a RunPod restart wipes the container disk, so an uploaded file would be lost while
the pod's configuration survives. Root and the provider host are already trusted
under the pilot's security contract, so the provider holding the client key adds no
new party.

Every host reads runtime bundles with one Terraform-managed key,
`gradiated/prod/nomad/host-runtime-reader`, limited to `GetObject` on the bundle
prefix, so registering a host needs no infrastructure change. Bundles hold released
runtime code, not weights or customer data.

### Running it

Ask for it through the ops MCP as a signed-in employee:

```
register_instance(provider: "runpod", instance_id: "<pod-id>")
instance_registration_status(registration_id: "<id>")
```

The first call checks the machine, starts registration and returns an id at once;
joining Nomad can take up to 30 minutes. Status moves through `recording`,
`issuing_certificate`, `updating_provider`, `waiting_for_node` and `bound`, or
`failed` with the reason. A running machine is refused: setting its image resets
it and can release scarce GPU capacity. Only when that reset is explicitly
authorized for that machine, call again with `reset_running_pod: true` and the
same id in `confirm_instance_id`. Every phase is audit-logged with the requesting
employee, provider, machine and reset flag.

The ops MCP holds everything registration needs. `kms:Sign` on the Nomad CA key
and the host runtime reader secret come from its pod identity role. Its `ops-mcp`
secret carries the RunPod API key, a database URL for the `gradiated_ops_mcp`
role (which may only write `instances`), the Nomad CA certificate and token, and
copies of the gateway runtime token and the RunPod deployment status token.
`NOMAD_BASE_IMAGE` in its manifest pins the host image by tag. The repository's
tags are immutable and named from a content hash, so the tag pins one image.

RunPod pulls `nomad-base` from `gradiated/prod/inference` through an ECR
delegation, not a stored registry login, so there is no ECR password to expire.
The repository policy (`registry-secrets`, `runpod_pull_repositories`) lets
RunPod's two fixed deployment roles pull, and the delegation is registered once
on the RunPod account with `POST https://api.runpod.io/v2/registries/delegations`
and the repository ARN. RunPod's v1 pod update also ignores
`containerRegistryAuthId`, so a stored login would never reach the pod.
RunPod applies the delegation only to tagged references: it pulls a
digest-only reference without credentials and refuses to create a pod from
`name:tag@digest`.
The immutable tagged index is retained by the untagged-only ECR lifecycle policy.
ECR also [protects child manifests referenced by a retained index](https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html),
so the 14-day cleanup cannot remove that base image indirectly.
The status list lives in memory, so a restart forgets it. Registering the machine
again finishes the job: a running machine that carries this instance's
bootstrap but whose node is not yet bound is resumed without a reset, and
registration waits for its node and binds it. A machine that is already
registered is refused, because renewing it needs `reset_running_pod`.

RunPod is the first provider. Setting the image resets the pod and also declares
the host proxy port, 8888; model weights belong on a volume. Registration adopts
an existing machine for now. Creating one from a SKU is a later addition to the
same interface, not a new path.

The instance row is the record of what was registered. RunPod is not under
Terraform, and the pilot assigns pod provisioning to the operator, so this tool
is that recorded operator path.

### What Nomad handles, and what it does not

Once a node has joined, Nomad handles runtime bundles, model versions, Desmond's
configuration, placement, rolling updates and restarts. Merging a job change rolls
it out. Two things stay outside it:

- The host image. The Nomad binary, device plugin and launcher are baked into
  `nomad-base`, so updating them is a provider image change and a reset. Moving
  more into job artifacts shrinks this.
- Host certificate renewal. Host certificates last 365 days. A dedicated issuer
  must authenticate the host, bind each CSR to its registered instance, refuse
  retired instances, and support replacement plus SIGHUP without resetting GPU
  hosts. Re-registration is not an acceptable steady-state renewal mechanism.

The control-plane certificates are automated: servers and UI use native renewal
sidecars, ops MCP and workers renew in memory, and deployment workflows and
`mise run nomad:admin` issue fresh client certificates for each invocation.
The worker and UI still use static read-only Nomad ACL tokens; Kubernetes
service-account JWT login is the remaining credential automation step for them.
RunPod REST v1 retires on 2026-11-15; registration must migrate to v2 before then.

## A job is a model deployment

Each `product/inference/nomad/jobs/<model>.nomad.hcl` declares one model's
deployment: the pinned runtime bundle, the replica count, what each replica needs,
its health checks and its rollout policy. Git is the desired state. There is no
placement table.

Each replica requests GPUs by type through Nomad's device plugin, which is how the
DeepSeek job asks for four B200s:

```hcl
device "nvidia/gpu" {
  count = 1
  constraint {
    attribute = "${device.model}"
    operator  = "regexp"
    value     = "RTX PRO 6000"
  }
}
```

Placement is Kubernetes-style. Nomad fingerprints every GPU on every enrolled node
and chooses where each replica goes. A job asking for two replicas of one GPU each
runs both on a two-GPU node, or on two of a four-GPU node's GPUs, leaving the rest
free for other jobs. Adding a node adds capacity without touching any job, and a job
whose replicas cannot all be placed waits until capacity appears.

Model jobs automatically reschedule failed allocations with bounded exponential
backoff. A one-hour disconnect grace preserves a running allocation through
control-plane outages; replacement still requires sufficient enrolled GPU capacity.

## Deploy on merge

A job is deployed when it has a committed `<job>.vars.hcl` beside it; a
qualification-only job has none and is never submitted. On merge to `main`, the
`Deploy jobs` workflow job plans and runs each deployable job. An unchanged job
updates in place without restarting anything. Changing job metadata changes
Nomad task environments and can replace allocations, so release-metadata
corrections must budget for model warmup too. Jobs whose public catalog ID differs
from their artifact name declare `runtime_model_name` explicitly; validation
rejects a missing mapping before deployment.

The workflow reaches the Nomad API through the tailnet and a Kubernetes
port-forward, and logs in with its GitHub OIDC token. Nomad's JWT auth method
turns that into a short-lived token with a policy that can submit and read jobs
and nothing else, bound to the `production` environment on `main`. No Nomad token
is stored anywhere.

Pull requests validate jobs but do not run `nomad job plan`. Planning needs the
`submit-job` capability, and a pull request can change its own workflow, so a
plan-capable token on pull requests would be a submit-capable token. The plan is
printed in the deploy log before each run instead.

## Deployments and routing

Nomad is the source of truth for which replicas exist; Desmond decides which are
routable.

- A replica's deployment id is its Nomad allocation id: model jobs set
  `DESMOND_DEPLOYMENT_ID = ${NOMAD_ALLOC_ID}`. A replacement allocation is a new
  deployment, so a dead replica's status can never keep its successor routable.
- A worker reconciler reads running allocations of model jobs and creates or
  retires the matching `model_deployments` rows. Desmond's reports are rejected
  until the row exists and stop mattering once it is gone.
- The gateway still picks the replica: readiness, capacity and affinity routing
  are unchanged.

Every host runs one authenticated ingress, the `host-proxy` system job, on the
single port the provider publishes (8888). It checks the gateway's bearer token
and forwards `/alloc/<allocation id>/` to that allocation's loopback runtime port,
which it learns from the Nomad service every model job registers as
`gradiated-runtime`.
Runtimes are never published and their ports can be dynamic, so any number of
allocations can share a host. A deployment's `service_url` is the host's
published address plus `/alloc/<allocation id>`; each provider supplies how that
port is reached (RunPod's HTTPS proxy, or TLS on a public or private IP).

Hosts enrolled by `register_instance` carry `serving_ingress = "host-proxy"`.
Hosts enrolled by hand before the proxy keep their own ingress on 8888 until
migrated.

## Catalog

Model definitions (identity, limits and prices) live in
`product/packages/control/src/catalog/models/`. The worker applies them on start and
every minute, so a merged change reaches production with the next release and a
direct database edit is put back. A retired model is removed from the catalog; its
row stays retired. There are no `configure-*` commands.

## Kev on Nomad

- A Kev runtime bundle: pinned upstream source, its environment, and the adapter.
- `kev-9b.nomad.hcl`: two replicas, one RTX PRO 6000 each.
- Desmond already probes any runtime's `/health`; the adapter adds `/metrics`,
  without which Desmond reports the replica as not accepting requests.
- Remove the hand-managed Kev pod setup from #91 — its supervisor programs, nginx
  proxy, `launch.sh` and `report_status.py`, which duplicates Desmond. The catalog
  entry and pricing stay; the release now comes from the job.

## Order

Each step is its own pull request.

1. `register_instance` with the RunPod provider, and `nomad-base` reading its bootstrap from the environment.
2. Deploy on merge.
3. The host proxy, the deployment reconciler and catalog apply.
4. Kev on Nomad, removing the hand-managed setup.
5. Run `register_instance` on the RTX 6000 pod, merge the Kev job, list the model, and
   verify a real decision through the SDK.

## Open

- Whether RunPod machines should move under Terraform. Until then the instance row
  is the record.
- Rescheduling and disconnect policy per job, once a node has spare GPUs.

### Safe model rollouts

Model updates launch one extra canary while existing replicas continue serving.
Nomad promotes it automatically only after all runtime and reporting checks stay
healthy, and reverts a failed deployment to its last stable job. Reserve enough
compatible GPU capacity for one extra replica; insufficient canary capacity must
leave the old service running rather than turn a rollout into an outage.

The Nomad deployment workflow follows each registration evaluation and waits for
new deployments to become healthy. Failure or rollback fails the release; queued
capacity and warmup have a bounded deadline. An unchanged deployment is not a new
release. The disposable recovery check is
`timeout 600 bash product/inference/nomad/tests/test-host-proxy.sh --recovery`.
It exercises task crashes, failed canary rollback, uninterrupted peer routes and
allocation replacement using the pinned Nomad binary and real host proxy.
### Replica availability alerts

Git's committed Nomad jobs also define the expected serving capacity, independent
of allocations and worker observations. After changing model jobs or replica
counts, run `node tools/nomad/model-replica-rules.mjs` and commit the generated
PrometheusRule with the job. Nomad validation rejects stale generated rules.
Argo deploys the rules; the worker dashboard shows desired, routed and ready counts.

`ModelNoReadyReplicas` is critical after five minutes with no fresh ready replica,
including missing jobs, unschedulable allocations and absent readiness metrics.
`ModelUnderReplicated` warns after ten minutes with some capacity but fewer ready
replicas than Git requires. An intentionally disabled model has zero replicas in
Git; keeping a catalog entry does not require a serving job. A queued deployment
with a positive desired count remains an actionable capacity deficit.

Cold starts longer than five minutes will alert when no existing replica serves.
Preserve healthy capacity through rollouts; do not silence readiness failures by
changing desired counts. Worker telemetry and loop alerts diagnose missing data.
