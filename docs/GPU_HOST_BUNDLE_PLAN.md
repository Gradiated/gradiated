# GPU host bundle plan

Status: proposal. Updated 2026-10-13.

## Problem

Everything that runs a GPU host is baked into the `gpu-base` image: the host
agent, supervisor, state helpers, Desmond, the proxy configuration logic and the
Tailscale scripts. CI builds a new image when any of them changes, but nothing
delivers that change to running hosts:

- **New hosts:** someone opens a PR to re-pin
  `infra/environments/prod/runpod/templates.json` and the ops-mcp workload (for
  example #530).
- **Running hosts:** we can't re-image a retained RunPod reservation, so someone
  copies files over SSH to each of the six hosts and signals the supervisor.
  `tools/gpu/install-host.py` can do the copy, but nothing runs it.

Host fixes therefore wait for manual work, hosts can drift from `main` without
anyone noticing, and nothing records which agent version each host runs.

Runtime bundles already solve this for models. The controller names a SHA-256,
and the host downloads, verifies and runs that tarball on an unchanged base.
This plan applies the same mechanism to host software.

## Target layout

### Thin base image: changes rarely and keeps the host reachable

| Component | Why it stays in the base |
|---|---|
| Ubuntu 24.04, CUDA 13 userspace, `python3`, system libraries | Runtime bundles are built against them. Changing them changes `base-id`. |
| Users (`runtime`, `desmond`, `downloader`) and directory layout | Ownership must hold before any bundle runs. |
| `sshd` and `bootstrap.py` enrollment | The way back in when everything else is broken. |
| Tailscale binaries and `install-tailscale.py` / `run-tailscale.sh` / `start-tailscale.sh` | If the host loses Tailscale, the controller can't reach it to fix it. |
| `nginx` binary | A system package. The agent writes its configuration. |
| `fetch-runtime`, `download-runtime`, `s5cmd` | The verified S3 download path, also used for host bundles. |
| **Host launcher** (new; replaces `supervise.py`) | Starts the selected host bundle, applies updates and rolls back. It never updates itself. |
| `base-id` | Declares which bundles are compatible. |

### Host bundle: changes often, delivered by the controller

| Component | Today |
|---|---|
| `host-agent.py`, `host_state.py` (including the model cache) | `/opt/gradiated/kubelet/` |
| `desmondd` (host copy) and `start-desmond` | `/opt/gradiated/kubelet/`, `/opt/gradiated/bin/` |
| Proxy configuration templates | Generated inside `host-agent.py` |
| Control bridge (`forward-control.py`, `run-control.sh`, `start-control.sh`) | `/opt/gradiated/tailscale-scripts/`. Moves in phase 4, after the update path has proven reliable, because breaking it stops Desmond reports but not SSH or Tailscale. |

The base keeps `runtime-launch` because the runtime bundle builds copy it from
there. Each runtime bundle already carries its own copy.

## Host launcher

The launcher is about 100 lines of standard-library Python, small enough to
review in full. It is the only host process that must never break.

- **Layout:** `/var/lib/gradiated-kubelet/host/<sha256>/` holds each unpacked
  host bundle. `current` and `previous` are symlinks to bundles, and `pending`
  records a requested update.
- **Start:** run `current/host-agent.py`. If `current` is missing or fails its
  `.bundle-sha256` check, use `previous`. If that also fails, use the copy baked
  into the base image. A host with no working bundle still starts an agent.
- **Update:** when `pending` names a staged and verified digest, point `current`
  at it, keep the old one as `previous`, and restart the agent the way SIGHUP
  does today. Model processes keep running, because agent restarts already
  preserve them (as #530 showed).
- **Health gate:** if the new agent doesn't answer `ping` on loopback with the
  new version within 120 seconds, or exits three times in ten minutes, the
  launcher points `current` back at `previous`, restarts, and records the
  failure.
- **Cleanup:** keep `current`, `previous` and one other verified bundle. Delete
  the rest.

## Update flow

1. **Build:** a new `host` target in `product/inference/bundles/build.hcl`
   packages the host bundle with the existing `package.sh`, verifies it on
   `runtime-base` (it imports and runs the agent test suite), and the model
   deployment workflow uploads it to S3 by SHA-256, the same as runtime bundles.
2. **Pin:** `infra/environments/prod/us-east-1/kubernetes/gpu-inference/host.json`
   names the desired host-bundle digest. `render-config.py` copies it into the
   controller ConfigMap, and CI rejects stale output. Shipping a host change is a
   PR that updates this one file. The release automation can open it, the way
   application releases update image digests.
3. **Stage:** the controller sends the digest with the existing `configure`
   operation. The agent stages it with the same download, verification and
   locking used for runtime bundles, then writes `pending`.
4. **Roll out:** the controller updates one host at a time. It waits until that
   host's `ping` reports the new digest and the host serves its pods for five
   minutes before moving to the next. If any host rolls back or stays unhealthy,
   it stops and reports through `GpuHostUpdateFailed`.
5. **Observe:** `ping` returns the running and previous host-bundle digests. The
   controller exports them as a metric, so a dashboard shows each host's version
   and drift alerts after 24 hours.

### Compatibility rules

- **HTTP API:** the agent's API (`ping`, `claim`, `configure`, `create`,
  `delete`, `status`, `list`) must stay compatible with the previous host bundle
  for at least one release, because the controller talks to mixed versions during
  a rollout.
- **On-disk state:** new code must read state the previous version wrote
  (`state.json`, `runtime.json`, cache markers), and add fields without renaming
  them.
- **Base requirement:** each host bundle declares the `base-id` it needs, and a
  host never stages a bundle for a different base.

## Migration

The six retained hosts run the `supervise.py` baked into their image, which
knows nothing about host bundles. They need one last manual SSH install of the
launcher and the first host bundle, done the same way as #530. After that they
update automatically. New hosts get the launcher from a re-pinned base image.

## Delivery

| Phase | Change | Done when |
|---|---|---|
| 0. Script the manual rollout | A command (or ops-mcp action) that installs agent files with `install-host.py` one host at a time, checks model and proxy process identities survived, and stops on the first failure | Rolling out #533 is one command, run by a person |
| 1. Host bundle build | `host` target in `build.hcl`, verification on `runtime-base`, S3 publish in the model deployment workflow | Each merge to `main` that touches host code publishes a verified host-bundle digest |
| 2. Launcher | New launcher in the base image; installed manually once on the six hosts; new base image pinned | Every host runs the launcher; a deliberately broken bundle rolls back in a test |
| 3. Controller-driven rollout | `host.json`, renderer and CI check, `configure` staging, one-host-at-a-time rollout, digest metric, `GpuHostUpdateFailed` | A host-agent PR reaches all six hosts after merge with no SSH |
| 4. Move the control bridge | Control bridge scripts move into the host bundle | One release of bridge changes ships automatically |

## Risks and open questions

- **The launcher is the new thing that must never break.** Keep it tiny, fully
  tested and independent of the agent. Have it fall back to the baked-in agent,
  so a corrupt bundle can't leave a host without one.
- **A bad bundle can pass the health gate.** It could answer `ping` and still
  mishandle pods. Rolling one host at a time with a five-minute soak limits that
  to one host, and Rollout and model alerts cover serving. Consider a canary host
  choice that avoids the only host for a model.
- **Trust.** The digest comes from Git through Argo, and hosts download only over
  short-lived grants and verify the SHA-256, the same as runtime bundles. That's
  no new trust. Signing bundles would be a later hardening step for both.
- **Base image changes are still manual and rare:** CUDA, Python, Tailscale and
  sshd changes still need a new base image and new hosts. Retained hosts can't
  get them. Keep `base-id` changes deliberate.
- **Open: control bridge timing.** Move it in phase 4 only if bridge changes keep
  happening. Otherwise it stays in the base.
