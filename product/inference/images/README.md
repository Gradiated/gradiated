# GPU images and runtime bundles

`gpu-base` contains Ubuntu, CUDA, system libraries, Python, nginx, fixed service
UIDs, the pinned Tailscale client and `gradiated-host`
([`../host`](../host)), which is the entrypoint and the enrollment command. It
contains no Desmond, host agent, downloader or model launcher, and no SSH server:
Tailscale SSH is the only shell access.

On first start, `gradiated-host start` stages the single-use key from
`GRADIATED_TAILSCALE_BOOTSTRAP_KEY` and joins the tailnet as
`gpu-bootstrap-<pod ID>` with Tailscale SSH, then removes the key from its
environment. It keeps tailscaled running, starts the control bridge and the host
agent launcher once enrollment has written their configuration, and restarts
any of them that exits.

Production pods use Tailscale's control server. The gpu-fleet end-to-end test
([`product/services/gpu-fleet/test/e2e`](../../services/gpu-fleet/test/e2e))
runs its own (headscale) and sets `GRADIATED_TAILSCALE_LOGIN_SERVER` to an
`https://<host>[:<port>]` origin; the first start records it with the pod ID, so
restarts and promotion use the same server. `gradiated-host` honours that
setting, and headscale's `hskey-auth-` keys, only on an image containing
`/etc/gradiated/test-control-server`, which only the test's image build adds; a
production image logs a warning and joins Tailscale. The operator's re-image
never carries `GRADIATED_TAILSCALE_*` settings forward from a pod's environment.

The build upgrades the Ubuntu packages inherited from NVIDIA's CUDA image and
keeps NVIDIA's CUDA packages at the pinned base versions. The ECR tag hashes the
build inputs, so a later Ubuntu security fix enters the image only after an input
changes, for example a newer CUDA base digest. Keep `base-id` unchanged for such
patch rebuilds: bundles carry it, and enrolled hosts reject bundles whose ID
differs from their own.

Ops MCP enrolls a bootstrap pod by running `gradiated-host enroll` over
Tailscale SSH with a typed JSON payload on stdin
([`enrollment-payload.schema.json`](../host/gradiated_host/enrollment-payload.schema.json)).
Enrollment installs the SHA-256-pinned host bundle, which contains the host
agent, launcher, downloader, Desmond and `runtime-launch`, keeps a verified copy
on disk for recovery, and stages promotion to `gpu-<instance ID>`
(`tag:gpu-inference`). Credentials travel only on stdin and through short-lived
artifact grants, never the provider environment. Running enrollment again with
the same payload is safe.

The image keeps copies of the host bundle's `host_bundle.py` and `host_state.py`
to verify the seed bundle, so changing either rebuilds the base image.

Model runtimes are not images: they are verified bundle archives built from
[`../bundles`](../bundles); every chat model bundle builds on SGLang. On RunPod,
the host agent executes those archives rather than starting nested Docker
containers. Kubernetes schedules resources and Argo Rollouts manages
replacement. The adapter supports trusted configured runtimes, not arbitrary
OCI workloads. Bare-metal deployments use ordinary kubelets and require OCI
packaging for their workloads.

Launchers preserve the assigned GPU mask and use a dynamic loopback runtime
port behind the private host proxy. The canonical pins and execution settings
live in `../gpu/runtimes.json`.

Runtime publication and production SDK qualification are separate checks. See
[release workflow](../../../tools/models/README.md).
