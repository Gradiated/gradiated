# GPU images and runtime bundles

`gpu-base` is the RunPod host image: CUDA and system libraries, launcher,
downloader, Tailscale, SSH and the host agent. Its bootstrap entrypoint enrolls
the host and stages pinned runtime bundles. Credentials are supplied externally,
cleared from child-process environments and never baked into an image.

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
