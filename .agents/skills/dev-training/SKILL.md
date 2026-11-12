---
name: dev-training
description: Search available GPU compute and prices across providers, get a spot or on-demand GPU VM (Nebius or Ornn) for development training or experiments, connect to it over Tailscale or SSH, and delete it afterwards. Use whenever an agent needs a GPU outside the serving fleet, including multi-node training; the VMs are isolated from production and from every other machine on the tailnet.
---

# Development training GPUs

`gradctl compute` creates GPU VMs from Nebius or Ornn for
training runs and experiments. Use it instead of leasing a serving host when the
work does not need production hardware.

| Provider | Virtualization | Sells | Spot ends | Notes |
| --- | --- | --- | --- | --- |
| Nebius | VM | presets from 1 GPU | preemption stops the VM with no warning | `start` resumes a stopped VM |
| Ornn | VM | whole nodes, often 8 GPUs | a reservation needing the GPUs ends it; a seller reclaim gives `preemptNoticeSeconds` (`/run/ornn/preemption.json`) | a resale market: prices and supply change hourly; on-demand also ends when the seller's listing ends; no stop or restart |

## Spot or on-demand

`--term spot` (the default) is spare capacity sold cheaply that the provider can
take back at any moment. `--term on-demand` costs about twice as much and is not
preempted. Use spot unless a run cannot checkpoint or the spot GPU is
unavailable. Either way, plan every run to survive losing the VM:

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
  region, provider or GPU type if capacity is short), restore from S3 and
  continue, then `down` the stopped VM.

## Isolation

We do not trust these providers with anything beyond the job on the VM. Each VM
joins the tailnet as `<provider>-<name>` with `tag:dev-training` and
`tag:dev-training-<provider>`. It can reach VMs from the same provider, for
multi-node training, and nothing else on the tailnet: no other provider's VMs,
inference GPUs, control plane, EKS, AWS, routers, relays or people's devices.
Machines tagged `tag:dev-machine` and administrators can reach every VM. The
tailnet policy tests in `infra/environments/prod/us-east-1/terraform/tailscale/policy.hujson`
enforce this. Keep a multi-node job on one provider.

Keep customer data, traces and production credentials off these VMs. They hold
only what you copy to them, and `gradiated/dev/env` holds only development keys.

## Before you start

- Credentials come from `gradiated/dev/env`. Load it into an ignored `.env` as
  AGENTS.md describes, or let the tool read it with the `gradiated-readonly`
  AWS profile.
- `mise install` provides the Nebius CLI, pinned in `mise.toml`; Ornn needs none.
- `gradctl` runs only on the Gradiated tailnet (`gradctl tailnet status`).
  Join a machine that is not on it as an ephemeral `tag:dev-machine` device
  with `gradctl tailnet join`, which reads `TAILSCALE_DEV_MACHINE_AUTH_KEY`.
  In a container without TUN, start `tailscaled --tun=userspace-networking` first.
- Pass `--json` for a result an agent can parse: `search` rows carry `up_args`,
  the exact arguments for `up`, and `up` returns the VM's address and tailnet
  names. `gradctl --json compute ssh <name> -- <command>` returns the remote
  command's exit code and output.
- State the hypothesis, GPU, expected hours and cost before `up`, as for any
  experiment.

## Use

1. Find compute: `gradctl compute search [--provider nebius,ornn] [--gpu h100]
   [--term spot] [--region us-] [--max-gpus 8] [--max-price 3]` lists what is
   available now, cheapest per GPU-hour first, with the provider,
   virtualization, GPUs per VM, how many such VMs can start now (`AVAIL`) and
   the arguments for `up`. Sold-out offers are hidden unless you pass `--all`.
   Nebius counts stop at our quota and are blank for shapes it does not
   report; Ornn counts are whole nodes for sale. Without `--provider` it
   searches every provider. `platforms --provider nebius --region <region>`
   lists every Nebius preset. Try the next offer if `up` fails.
2. Create: `gradctl compute up <name> <arguments from search> --max-price <USD per GPU-hour>`.
   Names are unique across providers, so `ssh`, `s3`, `start`, `stop` and `down`
   find the VM without `--provider`; `up` takes the provider from the platform
   name. `--max-price` refuses to buy if the price has
   moved above your limit; Ornn prepays each hour and refunds unused time.
   Ornn reservations have no names: the machine that ran `up` remembers the
   name, and `ls` elsewhere shows the reservation ID, which every command accepts.
3. Give the VM bucket access: `gradctl compute s3 <name>` installs a key that can
   only use the development training bucket as the VM's default AWS profile.
   VMs start with no credentials; do not copy any other key to them.
4. Connect: `gradctl compute ssh <name> [command]`, or
   `tailscale ssh root@<provider>-<name>` once it has joined the tailnet.
   Nodes of a multi-node job reach each other by MagicDNS name.
5. Sync checkpoints, results and logs to S3 on a schedule as the job runs (see
   above). Nothing on the VM is backed up.
6. `gradctl compute ls` shows every VM. A preempted Nebius VM shows as stopped and
   still pays for its disk. Resume on a new VM from S3; `start` the old one only
   if the new one cannot be created, and `down` whichever you no longer need. An
   ended Ornn VM is gone with its disk.
7. Delete as soon as you are done: `gradctl compute down <name>` deletes the VM,
   its disk and its tailnet device. If it fails part way, run it again.

Report the VM, its hours and where the results are in your response or PR.

## Adding a provider

Add a module beside `nebius.py` and `ornn.py` in
`tools/gradctl/src/gradctl/compute/` with the same attributes
(`virtualization`, `cloud_init`, `ephemeral`) and methods (`regions`,
`platforms`, `offers`, `find`, `list`, `create`, `start`, `stop`, `delete`) and
register it in `PROVIDERS`. `create` must run the cloud-init the tool passes; a
provider without cloud-init sets `cloud_init = False` and the tool joins the VM
over SSH. Add `tag:dev-training-<provider>`, owned by `tag:terraform` (never by a
node tag), with its grant, SSH rule and tests in the tailnet policy, and add the
provider to `dev_training_provider` in `infra/modules/tailscale/credentials.tf`. Give the provider
its own SSH key and a setup script that writes `<PROVIDER>_*` keys to
`gradiated/dev/env`, with development-only credentials. Check that the
provider's account-level access (such as RunPod's SSH proxy, which gives every
account key root on every pod) cannot reach production machines; use a separate
account if it can.
