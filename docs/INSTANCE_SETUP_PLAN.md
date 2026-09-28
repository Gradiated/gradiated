# Instance registration and Nomad-managed model deployments

Status: agreed direction. Step 1, instance registration, is implemented. Builds on the
[Nomad serving pilot](NOMAD_SERVING_PILOT_PLAN.md), which this does not replace.

## Goal

Adding GPU capacity is one command that puts only a trust bootstrap on the machine. Deploying a model is one merged file. Nobody
uploads runtimes to a host or writes service URLs by hand.

```
pnpm instance:register <provider> <provider-instance-id>
  → instance row + host credentials + Gradiated host image + Nomad node joined

merge product/inference/nomad/jobs/<model>.nomad.hcl
  → CI submits it → Nomad places replicas on eligible GPUs → each allocation
    registers itself and reports status → the gateway routes to it
```

## Instance registration

`instance:register` is a TypeScript operator command beside the `configure-*`
operations in `product/services/api`. The provider is its first argument and selects
an implementation of one interface, so a second provider is a new implementation
rather than a new command.

```ts
interface InstanceProvider {
  // Identify an existing machine and read what it is: account, SKU, location.
  describe(providerInstanceId: string): Promise<ProviderInstance>;
  // Point it at the host image and hand it its bootstrap.
  bootstrap(instance: ProviderInstance, image: HostImage, environment: Record<string, string>): Promise<void>;
}
```

Registration puts only the trust bootstrap on the machine, because that is the one
thing Nomad cannot deliver: it cannot give a node the credentials it needs to join
Nomad. Everything after that is Nomad's job. The command:

1. Records the `instances` row from `describe`. Provider, account and instance id
   are the unique identity; registering the same machine again keeps its instance
   id, and a replacement machine is a new row.
2. Issues the instance's own Nomad client certificate, signed by the private CA
   (ECDSA — the client rejects Ed25519). Credentials are per instance, never per GPU
   or per provider.
3. Reuses the bound node's id and secret from the machine's current configuration,
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

```
kubectl -n nomad port-forward svc/nomad-api 4646
NOMAD_ADDR=https://127.0.0.1:4646 NOMAD_TOKEN=... \
NOMAD_CACERT=ca.pem NOMAD_CLIENT_CERT=cli.pem NOMAD_CLIENT_KEY=cli-key.pem \
NOMAD_BASE_IMAGE=<account>.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference@sha256:... \
DATABASE_URL=... RUNPOD_API_KEY=... \
pnpm --filter @gradiated/api instance:register runpod <pod-id>
```

The Nomad variables are the Nomad CLI's own: the operator certificate from
`gradiated/prod/nomad/operator` and the read-only token from `gradiated/prod/nomad/ui-acl`.
AWS access comes from the operator's CLI session.

RunPod is the first provider. Setting the image resets the pod; model weights
belong on a volume. The command adopts an existing machine for now. Creating one
from a SKU is a later addition to the same interface, not a new path.

The instance row is the record of what was registered. RunPod is not under
Terraform, and the pilot assigns pod provisioning to the operator, so this command
is that recorded operator path.

### What Nomad handles, and what it does not

Once a node has joined, Nomad handles runtime bundles, model versions, Desmond's
configuration, placement, rolling updates and restarts. Merging a job change rolls
it out. Two things stay outside it:

- The host image. The Nomad binary, device plugin and launcher are baked into
  `nomad-base`, so updating them is a provider image change and a reset. Moving
  more into job artifacts shrinks this.
- Certificate renewal. Nomad does not renew client certificates, so re-running
  `instance:register` is the renewal path until a dedicated one exists.

## A job is a model deployment

Each `product/inference/nomad/jobs/<model>.nomad.hcl` declares one model's
deployment: the pinned runtime bundle, the replica count, what each replica needs,
its health checks and its rollout policy. Git is the desired state. There is no
placement table.

Each replica requests GPUs by type through Nomad's device plugin, which is how the
DeepSeek job already asks for four B300s:

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

The DeepSeek job is deliberately conservative: `distinct_hosts`, no rescheduling,
no replacement on disconnect, because it had no spare capacity. Jobs that want
self-healing enable rescheduling instead.

## Deploy on merge

A job is deployed when it has a committed `<job>.vars.hcl` beside it; a
qualification-only job has none and is never submitted. On merge to `main`, the
`Deploy jobs` workflow job plans and runs each deployable job. An unchanged job
updates in place without restarting anything.

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

Hosts enrolled by `instance:register` carry `serving_ingress = "host-proxy"`.
Hosts enrolled by hand before the proxy keep their own ingress on 8888 until
migrated.

## Kev on Nomad

- A Kev runtime bundle: pinned upstream source, its environment, and the adapter.
- `kev-9b.nomad.hcl`: two replicas, one RTX PRO 6000 each.
- A decision-runtime probe in Desmond, which today only understands vLLM.
- Remove the hand-managed Kev pod setup from #91 — its supervisor programs, nginx
  proxy, `launch.sh` and `report_status.py`, which duplicates Desmond. The catalog
  entry, pricing and release digest stay.

## Order

Each step is its own pull request.

1. `instance:register` with the RunPod provider, and `nomad-base` reading its bootstrap from the environment.
2. Deploy on merge.
3. The host proxy, the deployment reconciler and catalog apply.
4. Kev on Nomad, removing the hand-managed setup.
5. Run `instance:register` on the RTX 6000 pod, merge the Kev job, list the model, and
   verify a real decision through the SDK.

## Open

- Whether RunPod machines should move under Terraform. Until then the instance row
  is the record.
- Rescheduling and disconnect policy per job, once a node has spare GPUs.
