# GPU images and runtime bundles

`gpu-base` contains Ubuntu, CUDA, system libraries, Python, nginx, OpenSSH,
fixed service UIDs, the pinned Tailscale client with its supervisor scripts, and
minimal init startup. It contains no Desmond, host agent, downloader, enrollment
implementation or model launcher. Application changes do not participate in its
build identity. On first start, the init loop stages the single-use bootstrap key
from `GRADIATED_TAILSCALE_BOOTSTRAP_KEY` and joins the tailnet as
`gpu-bootstrap-<pod ID>` with Tailscale SSH. It never starts public OpenSSH
unless `GRADIATED_BREAK_GLASS_SSH=1` and `PUBLIC_KEY` are set, and it removes
root's `authorized_keys` otherwise. It keeps the Tailscale supervisor running,
waits for completed enrollment, supervises the installed bootstrap, and restarts
it if it exits. The bootstrap and recovery implementation remain on disk.

The build upgrades the Ubuntu packages inherited from NVIDIA's CUDA image and
keeps NVIDIA's CUDA packages at the pinned base versions. The ECR tag hashes the
build inputs, so a later Ubuntu security fix enters the image only after an input
changes, for example a newer CUDA base digest. Keep `base-id` unchanged for such
patch rebuilds: bundles carry it, and enrolled hosts reject bundles whose ID
differs from their own.

Enrollment installs a SHA-256-pinned host archive over Tailscale SSH. The
archive contains enrollment, supervision and recovery, the downloader, Desmond,
`runtime-launch`, and private control forwarding. A verified seed is retained on
disk for recovery; it is independent of the image. Credentials travel through
SSH stdin and short-lived artifact grants, never the provider environment.

Publish and qualify the new host archive before selecting this base for new
pods. Configure Ops MCP `GPU_HOST_BOOTSTRAP_SHA256` with that release's digest
(`bootstrapVersion: 1`), apply its scoped artifact-read IAM policy, and then update
the approved `GPU_BASE_IMAGE` and provisioning template. An older host archive
without enrollment files is rejected before activation. Existing reservations
are upgraded in place; changing their provider image is unnecessary.

Install the new host bundle before rolling out model archives that omit
`runtime-launch`. Existing model archives remain supported by the host agent's
legacy launcher fallback. Hosts enrolled before the v5 template are re-imaged
onto it. The connection-preserving forwarding dispatcher is installed at new
enrollment; legacy forwarding listeners need a separate controlled migration.

The model image directories provide pinned runtime packaging and launch scripts.
On RunPod, the host agent executes verified archives rather than starting nested
Docker containers. Kubernetes schedules resources and Argo Rollouts manages
replacement. The adapter supports trusted configured runtimes, not arbitrary
OCI workloads. Bare-metal deployments use ordinary kubelets and require OCI
packaging for their workloads.

GLM reserves two GPUs; DeepSeek reserves four. Launchers preserve the assigned
GPU mask and use a dynamic loopback runtime port behind the private host proxy.
The canonical pins and execution settings live in `../gpu/runtimes.json`.

```sh
bash product/inference/images/tests/test_launch.sh
```

These checks verify launch arguments and environment handling without a GPU.
Runtime publication and production SDK qualification are separate checks. See
[release workflow](../../../tools/models/README.md).
