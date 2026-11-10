---
name: dev-training
description: Get a spot GPU VM for development training or experiments, connect to it over Tailscale or SSH, and delete it afterwards. Use whenever an agent needs a GPU outside the serving fleet, including multi-node training; the VMs are isolated from production and from every other machine on the tailnet.
---

# Development training GPUs

`tools/dev-training/dev_training.py` creates spot GPU VMs from a supported
provider (Nebius for now) for training runs and experiments. Use it instead of
leasing a serving host when the work does not need production hardware.

## This is spot capacity

These VMs are spare capacity sold cheaply, and the provider can take one back
at any moment with no warning. Plan every run to survive that:

- Treat the VM's disk as scratch. Anything that exists only on the VM can be
  lost at any time.
- Save checkpoints, metrics, logs and results to the development training
  bucket (`DEV_TRAINING_S3_BUCKET` in `gradiated/dev/env`) under
  `s3://<bucket>/<project>/<run>/`, regularly while the job runs, not only at
  the end: at least every 15 to 30 minutes of GPU work, and
  after every evaluation or milestone. Choose an interval you would be content
  to lose.
- Make the job resumable: on start, look for the latest checkpoint in S3 and
  continue from it. Keep the exact command, code revision and configuration
  with the checkpoint, so any VM can pick it up.
- When a VM is preempted, do not wait for it. Create another one (another
  region or GPU type if capacity is short), restore from S3 and continue, then
  `down` the stopped VM.

## Isolation

Each VM joins the tailnet as `<provider>-<name>` with `tag:dev-training`. It can
reach other `tag:dev-training` VMs, for multi-node training, and nothing else on
the tailnet: no inference GPUs, control plane, AWS, routers, relays or people's
devices. Machines tagged `tag:dev-machine` and administrators can reach it. The
tailnet policy tests in `infra/environments/prod/us-east-1/terraform/tailscale/policy.hujson`
enforce this.

Keep customer data, traces and production credentials off these VMs. They hold
only what you copy to them, and `gradiated/dev/env` holds only development keys.

## Before you start

- Credentials come from `gradiated/dev/env`. Load it into an ignored `.env` as
  AGENTS.md describes, or let the tool read it with the `gradiated-readonly`
  AWS profile.
- Install the provider CLI the tool asks for (Nebius:
  `curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash`).
- To use Tailscale from a machine that is not on the tailnet, join it as an
  ephemeral `tag:dev-machine` device:
  `tailscale up --auth-key="$TAILSCALE_DEV_MACHINE_AUTH_KEY" --advertise-tags=tag:dev-machine`.
  In a container without TUN, start `tailscaled --tun=userspace-networking` first.
  Without Tailscale, `dev_training.py ssh` still works over the VM's public IP.
- State the hypothesis, GPU, expected hours and spot cost before `up`, as for any
  experiment.

## Use

1. Pick a GPU: `dev_training.py capacity [platform]` shows, for every region and
   preset, whether spot and on-demand capacity is available now and your quota
   (`available/limit`). `platforms --region <region>` lists what each region offers.
   Spot capacity changes quickly; pick a region with spot availability.
2. Create: `dev_training.py up <name> --platform <platform> --preset <preset> [--region <region>]`.
   Names are unique per provider. The VM is billed at the spot price.
3. Give the VM bucket access: `dev_training.py s3 <name>` installs a key that can
   only use the development training bucket as the VM's default AWS profile.
   VMs start with no credentials; do not copy any other key to them.
4. Connect: `dev_training.py ssh <name> [command]`, or
   `tailscale ssh root@<provider>-<name>` once it has joined the tailnet.
   Nodes of a multi-node job reach each other by MagicDNS name.
5. Sync checkpoints, results and logs to S3 on a schedule as the job runs (see
   above). Nothing on the VM is backed up.
6. `dev_training.py ls` shows every VM. A preempted VM shows as stopped and still
   pays for its disk. Resume on a new VM from S3; `start` the old one only if the
   new one cannot be created, and `down` whichever you no longer need.
7. Delete as soon as you are done: `dev_training.py down <name>` deletes the VM,
   its disk and its tailnet device. If it fails part way, run it again.

Report the VM, its hours and where the results are in your response or PR.

## Adding a provider

Add a module beside `nebius.py` with the same methods (`regions`, `platforms`,
`find`, `list`, `create`, `start`, `stop`, `delete`) and register it in
`PROVIDERS`. `create` must run the cloud-init the tool passes, which installs
Tailscale and joins with a single-use `tag:dev-training` key. Give the provider
its own SSH key and a setup script that writes `<PROVIDER>_*` keys to
`gradiated/dev/env`, with development-only credentials. Check that the
provider's account-level access (such as RunPod's SSH proxy, which gives every
account key root on every pod) cannot reach production machines; use a separate
account if it can.
