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

## Commands

Run `gradctl commands` for the current list.

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
