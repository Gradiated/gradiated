# GPU images and runtime bundles

`gpu-base` contains Ubuntu, CUDA, system libraries, Python, nginx, OpenSSH,
fixed service UIDs and minimal SSH startup. It contains no Desmond, host agent,
downloader, enrollment implementation or model launcher. Application changes do
not participate in its build identity.

Enrollment installs a SHA-256-pinned host archive over authenticated SSH. The
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
legacy launcher fallback. Existing hosts retain their installed SSH/Tailscale
supervisors. The connection-preserving forwarding dispatcher is installed at new
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
