# gradctl

`gradctl` is the one CLI for developer and agent operations at Gradiated:
DevEx checks, the `.env` and AWS sign-in, development training GPUs, GPU host
leases and the GPU fleet tools. It is written for agents first: every command
describes itself, `--json` gives one parseable result, exit codes are stable and
no command prompts.

## Install

In the repository, `mise install` provides everything gradctl runs on, and mise
puts `gradctl` on PATH (`[env] _.path` in `mise.toml`). It runs from the
checkout with nothing else to install, wherever mise is active: an activated
shell, `mise exec` or a mise task. mise pins:

- Python 3.13. Installing it also installs `tools/python-requirements.txt` (PyYAML
  and the other packages the repository's Python tools import). After changing
  that file, run `mise run python:deps`.
- The Nebius CLI, for `compute`.
- `aws`, `kubectl`, `node` and `cargo`, which other commands use.

Only Tailscale comes from the machine, because it is a system service.
`gradctl devex doctor` reports every tool and package.

Outside a checkout, or without mise:

```sh
mise run gradctl:install        # one file at ~/.local/bin/gradctl
tools/gradctl/gradctl ...      # run it from a checkout directly
uv tool install --editable tools/gradctl   # or follow the checkout as you edit it
```

The installed file is a Python zipapp that needs only `python3` 3.10 or newer
and the standard library, so it runs on any developer machine, VM or CI runner.
Copy it anywhere: it needs no checkout. Commands that work on the repository
find the checkout from the working directory, or from `GRADCTL_REPO`. Rerun the
install after pulling to pick up changes; `gradctl version` shows the commit
it was built from.

## The tailnet

Every command needs the machine on the Gradiated tailnet (`gradiated.com`).
`gradctl tailnet status` reports the connection and exits 3 when it is down.
A person signs in with the Tailscale app. A headless machine, such as a cloud
VM or an agent sandbox, joins as an ephemeral `tag:dev-machine` device with
`gradctl tailnet join`, which reads `TAILSCALE_DEV_MACHINE_AUTH_KEY` from the
environment or `gradiated/dev/env`. In a container without TUN, start
`tailscaled --tun=userspace-networking` first, and set `TAILSCALE_SOCKET` if it
listens somewhere other than the default socket.

`aws login` and `env build` also run off the tailnet: they are how a new machine
gets the key that joins it. Everything else refuses with exit code 3.

The tailnet check does not grant access: the tailnet policy and AWS IAM do. It
means every caller works from the same network position, so no command half-runs
on a machine that cannot reach the fleet, the cluster or the dev-training VMs.

GitHub Actions runners are not on the tailnet. There, commands with
`network: false` (DevEx checks, config rendering, the lab check) run without it,
and every other command still refuses.

## For agents

```sh
gradctl commands --json                  # every command, its arguments, effects and requirements
gradctl --json compute search --gpu h100 # one envelope on stdout
```

With `--json` (anywhere on the command line, or `GRADCTL_JSON=1`), stdout holds
exactly one JSON document, and progress and subprocess output go to stderr:

```json
{"ok": true, "command": "compute search", "data": [...]}
{"ok": false, "command": "compute up", "data": null,
 "error": {"code": "tailnet_required", "message": "...", "hint": "..."}}
```

| Exit | Code | Meaning |
| --- | --- | --- |
| 0 | | ok |
| 1 | `failed` and others | the command ran and did not succeed |
| 2 | `usage` | bad arguments; nothing was done |
| 3 | `tailnet_required` | not connected to the Gradiated tailnet |
| 4 | `repo_required` | the command needs a checkout |
| 5 | `dependency_missing` | `aws`, `kubectl`, `nebius` or another tool is not installed |

Each catalog entry says what a command does before you run it:

- `effects`: `read`, `write` (changes something and is safe to rerun) or
  `destructive` (`compute down` and `gpu lease release` delete a VM or wipe a host).
- `network`, `repo`, `requires`: what it needs.
- `interactive`: it opens a browser sign-in (`aws login`, `env build`) or a
  shell (`compute ssh` without a command). Under `--json`, `compute ssh` needs a
  command and returns its exit code and output.
- `forwards_args`: arguments after the command go unchanged to a repository
  tool. Use `--` before them when one could be mistaken for gradctl's own, for
  example `gradctl gpu render-config -- --help`.

## SF Compute training GPUs

`gradctl compute search --provider sfcompute` reads live SKU-specific market quotes
using `SF_COMPUTE_API_TOKEN` from `gradiated/dev/env`. Instance lookups and lifecycle
commands are scoped to `SF_COMPUTE_WORKSPACE`. Prices are USD per GPU-hour;
SF Compute buys whole nodes. Quotes cover the window ending at the last provider
schedule boundary within one hour, and do not guarantee availability.

Before provisioning, merge and deploy the Tailscale provider tag/OAuth client in
this change, then run `gradctl compute setup tailscale` to copy its credentials
and `gradctl compute setup sfcompute` to store a dedicated SSH key and workspace
in the shared development secret. Both setup commands require AWS write access;
they do not buy compute. With multiple workspaces, set `SF_COMPUTE_WORKSPACE` to
the chosen workspace ID or resource path first. The API token is the only SF
credential that needs to be supplied manually.

```sh
gradctl compute search --provider sfcompute --gpu h100
gradctl compute up train-sf --provider sfcompute --platform <sku_id> \
  --term on-demand --max-price 3 --duration-hours 4
gradctl compute ssh train-sf --provider sfcompute -- nvidia-smi
gradctl compute down train-sf --provider sfcompute
```

`up` requires a finite positive `--max-price` and buys one node with a non-standing,
non-partial order into a dedicated `gradctl-<name>` pool. The price cap rounds down
to a market tick. `--duration-hours` defaults to 1 and is an upper bound: the end
is the last provider schedule boundary inside that window. There is no automatic
renewal. Before expiry, extend with a new price cap:

```sh
gradctl compute extend train-sf --provider sfcompute --hours 2 --max-price 3
```

This buys a contiguous block on the same pool/SKU without replacing the VM.
`--hours` (alias `--duration-hours`) bounds the added time; the end rounds down
to a provider schedule boundary. Extensions require an active, dedicated one-node
gradctl pool with no allocation gaps or outstanding buy orders. An expired or
terminated instance cannot be revived. Identical order bodies use the same
idempotency key; ambiguous responses still require reconciliation before retrying.

Nebius VMs run until stopped/deleted or preempted, Ornn hourly rentals renew
automatically until ended, and Spheron GPU VMs bill while running. Their supported
rental APIs have no explicit extension operation; `extend` explains this and
does not submit a purchase. It cannot override seller listing ends or spot reclaim.

Spot uses SF Compute's preview resale/preemption feature (1.2 times the
buy limit, the API maximum); a 30% markup is not supported. The multiplier uses
the order's price limit rather than its actual fill price. On extension this
applies to the new block's buy limit. On-demand omits this feature. Both terminate
at allocation expiry. VMs use
cloud-init, root SSH, and the public Ubuntu 24.04/CUDA 13.2 image by default;
`--image` accepts another SF image ID/resource path. Stop/resume is unsupported.

**`down` deletes the VM but does not refund prepaid compute.** Remaining time stays
in its pool until expiry; sell unused time through SF Compute. Pools are retained
so failed or ambiguous purchases remain inspectable. Reusing a name with an
existing pool is refused to prevent a second purchase. Inspect the pool/orders in
the console before retrying; mutations are never automatically retried. `meter`
weights actual buy-order fill rates by their overlap with each usage interval,
including extension blocks, and caps terminal usage intervals at allocation expiry
(or an earlier provider-observed termination update). It excludes unused prepaid
time, fees, and resale credits. Instances without a tracked order
keep pricing unknown. Provider billing remains the source of truth for total spend.

The REST contracts are documented in SF Compute's
[instance API](https://docs.sfcompute.com/api-reference/instances/create-instance),
[order API](https://docs.sfcompute.com/api-reference/orders/create-order), and
[market quote API](https://docs.sfcompute.com/api-reference/orderbook/get-market-quote).

## Commands

Run `gradctl commands` for the current list.

| Group | Commands |
| --- | --- |
| `tailnet` | `status`, `join` |
| `devex` | `start` (the first command of every agent turn), `check`, `context`, `doctor`, `skills` |
| `env` / `aws` | `env build` writes `.env` from `gradiated/dev/env`; `aws login [--profile]` |
| `compute` | `search`, `platforms`, `up`, `ls`, `ssh`, `s3`, `start`, `stop`, `down`, `setup`; see `$dev-training` |
| `gpu lease` | `acquire`, `wait`, `extend`, `release`, `status`; see `$gpu-host-lease` |
| `gpu` | `render-config`, `stage-glm-pool`, `stage-kimi-pool`, `pin-host`, `prepare-enrollment`, `mint-bootstrap-key`, `create-runpod-template`, `qualification-slot` |
| `infra` | `fmt`, `check`, `sec` |
| `security` | `drata-policies`, `drata-risks`, `argocd-auth`, `temporal-ui`, `audit-controls`, `unauthorized-calls`, `ci-boundaries` |
| `observability` | `check`, `platform`, `controller-requests` |
| `models` | `monitoring-billing`, `probe-readiness` |
| `browser` | `sync`, `install`, `website-screenshots`, `storybook-screenshots`, `temporal-ui` |
| `product` | `sglang-local`, `temporal-ui-local`, `opencode`, `desmond-build-image`, `desmond-test` |
| `github-apps`, `lab`, `research` | `create`; `check`; `efficiency` |

## Layout

- `src/gradctl/cli.py`: the parser, the catalog, the envelope and the dispatcher.
- `src/gradctl/core.py`: command metadata, results, errors and exit codes.
- `src/gradctl/tailnet.py`: the tailnet requirement and `tailnet join`.
- `src/gradctl/devex.py`, `envfile.py`, `lease.py`, `compute/`: the commands
  gradctl implements itself. They run from the single file, without a checkout.
- `src/gradctl/repotools.py`: the repository tools gradctl runs from the
  checkout. These (`tools/gpu/*.py` and others) change files beside them and CI
  runs some by path, so they stay where they are and gradctl is their front door.

## Adding a command

Add it to gradctl, not as a standalone script, mise task or Makefile target.
Register it with `leaf(...)` and a `Meta` that states its effects and needs, and
return a `Result` whose `data` is JSON-serializable and whose `text` is the
human output. Raise `CliError`, or call `sys.exit("message")`, to fail. Keep it
to the standard library so the single file keeps working everywhere. A tool
that must stay in the repository goes in `repotools.TOOLS`.

```sh
python3 -m unittest discover -s tools/gradctl/tests
tools/gradctl/gradctl devex check
python3 tools/gradctl/build.py && .agents/runtime/gradctl/gradctl commands
```
