# grad-ctl

`grad-ctl` is the one CLI for developer and agent operations at Gradiated:
DevEx checks, the `.env` and AWS sign-in, development training GPUs, GPU host
leases and the GPU fleet tools. It is written for agents first: every command
describes itself, `--json` gives one parseable result, exit codes are stable and
no command prompts.

## Install

In the repository, mise puts `grad-ctl` on PATH (`[env] _.path` in
`mise.toml`), so it runs from the checkout with nothing to install, wherever mise
is active: an activated shell, `mise exec` or a mise task. mise also pins `aws`,
`kubectl`, `node` and `cargo`, which some commands use. It does not provide
Python 3.10+ or Tailscale; those come from the machine, and `grad-ctl devex doctor` reports
both. Python stays the system one because the GPU fleet tools import PyYAML from
it.

Outside a checkout, or without mise:

```sh
mise run grad-ctl:install        # one file at ~/.local/bin/grad-ctl
tools/grad-ctl/grad-ctl ...      # run it from a checkout directly
uv tool install --editable tools/grad-ctl   # or follow the checkout as you edit it
```

The installed file is a Python zipapp that needs only `python3` 3.10 or newer
and the standard library, so it runs on any developer machine, VM or CI runner.
Copy it anywhere: it needs no checkout. Commands that work on the repository
find the checkout from the working directory, or from `GRAD_CTL_REPO`. Rerun the
install after pulling to pick up changes; `grad-ctl version` shows the commit
it was built from.

## The tailnet

Every command needs the machine on the Gradiated tailnet (`gradiated.com`).
`grad-ctl tailnet status` reports the connection and exits 3 when it is down.
A person signs in with the Tailscale app. A headless machine, such as a cloud
VM or an agent sandbox, joins as an ephemeral `tag:dev-machine` device with
`grad-ctl tailnet join`, which reads `TAILSCALE_DEV_MACHINE_AUTH_KEY` from the
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
grad-ctl commands --json                  # every command, its arguments, effects and requirements
grad-ctl --json compute search --gpu h100 # one envelope on stdout
```

With `--json` (anywhere on the command line, or `GRAD_CTL_JSON=1`), stdout holds
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
  tool. Use `--` before them when one could be mistaken for grad-ctl's own, for
  example `grad-ctl gpu render-config -- --help`.

## Commands

Run `grad-ctl commands` for the current list.

| Group | Commands |
| --- | --- |
| `tailnet` | `status`, `join` |
| `devex` | `start` (the first command of every agent turn), `check`, `context`, `doctor`, `skills` |
| `env` / `aws` | `env build` writes `.env` from `gradiated/dev/env`; `aws login [--profile]` |
| `compute` | `search`, `platforms`, `up`, `ls`, `ssh`, `s3`, `start`, `stop`, `down`, `setup`; see `$dev-training` |
| `gpu lease` | `acquire`, `wait`, `extend`, `release`, `status`; see `$gpu-host-lease` |
| `gpu` | `render-config`, `stage-glm-pool`, `stage-kimi-pool`, `pin-host`, `pin-sglang-pools`, `prepare-enrollment`, `mint-bootstrap-key`, `create-runpod-template`, `qualification-slot` |
| `github-apps`, `browser`, `lab` | `create`; `sync`, `install`; `check` |

## Layout

- `src/grad_ctl/cli.py`: the parser, the catalog, the envelope and the dispatcher.
- `src/grad_ctl/core.py`: command metadata, results, errors and exit codes.
- `src/grad_ctl/tailnet.py`: the tailnet requirement and `tailnet join`.
- `src/grad_ctl/devex.py`, `envfile.py`, `lease.py`, `compute/`: the commands
  grad-ctl implements itself. They run from the single file, without a checkout.
- `src/grad_ctl/repotools.py`: the repository tools grad-ctl runs from the
  checkout. These (`tools/gpu/*.py` and others) change files beside them and CI
  runs some by path, so they stay where they are and grad-ctl is their front door.

## Adding a command

Add it to grad-ctl, not as a standalone script, mise task or Makefile target.
Register it with `leaf(...)` and a `Meta` that states its effects and needs, and
return a `Result` whose `data` is JSON-serializable and whose `text` is the
human output. Raise `CliError`, or call `sys.exit("message")`, to fail. Keep it
to the standard library so the single file keeps working everywhere. A tool
that must stay in the repository goes in `repotools.TOOLS`.

```sh
python3 -m unittest discover -s tools/grad-ctl/tests
tools/grad-ctl/grad-ctl devex check
python3 tools/grad-ctl/build.py && .agents/runtime/grad-ctl/grad-ctl commands
```
