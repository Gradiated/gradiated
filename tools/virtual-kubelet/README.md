# RunPod Virtual Kubelet prototype

This tests whether the Kubernetes scheduler and Deployment controller can manage
processes inside an existing RunPod container. It uses Virtual Kubelet v1.11.0
and pinned SSH. It does not create, reset, update or terminate RunPod pods.

The controller runs beside an isolated local Kubernetes API. Kubernetes
credentials stay on that machine. A root-owned Python helper on an idle RunPod
host starts a fixed smoke process as UID 65534, with an empty GPU visibility
mask and no inherited credentials. Pod deletion terminates that process group;
it does not release the provider reservation. The helper records process birth
times to avoid signalling a different process after PID reuse. Smoke processes
expire after ten minutes even if the controller disappears.

The virtual node advertises two CPUs, 1 GiB of memory and eight pod slots. These
are scheduler accounting values, not enforced process limits. It advertises no
GPUs by default. Only the `vk-trial` namespace and the fixed CPU/GPU discovery
workloads are accepted. Their image names identify the helper's built-in
processes; no container image is pulled or executed.

The binary deliberately rejects Kubernetes API endpoints outside HTTPS on
`127.0.0.1`. This is a feasibility test, not an EKS deployment manifest.

The live smoke test passed on an existing four-B300 RunPod host: CPU Deployment
scaling from two to three replicas and back to one, preservation of remote
process IDs across controller restart, GPU discovery with a 2+1+1 allocation,
and a fourth GPU pod remaining Pending because capacity was exhausted. No model
processes or provider configuration were changed. This establishes feasibility
of basic scheduling and process management, not production serving readiness.

## Run the smoke test

Use an idle host with pinned SSH credentials. Run a local K3s control plane,
without worker agents, using this image:

```text
rancher/k3s@sha256:fd4740667b7033055c27d424d0d2d660bf66cedbdb225d68e0eab6dd48aa0fd2
```

Start it with `server --disable-agent
--disable=traefik,servicelb,metrics-server,local-storage --tls-san=127.0.0.1`,
and publish its API port only on local loopback. Copy the generated kubeconfig
to a mode-0600 file outside the repository and change its server port to the
published port. Every kubectl command below must use that isolated kubeconfig.

Build and test with Go 1.24:

```sh
cd tools/virtual-kubelet
go test ./...
go build -o /tmp/runpod-vk .
python3 remote_test.py
```

The Python process-lifecycle test needs root to drop the test workload to UID
65534. It uses temporary local files and does not contact RunPod.

Create a root-owned `/tmp/gradiated-vk-<unique trial ID>` directory on the host,
then copy `remote.py` into it using pinned SSH/SCP. Start the controller:

```sh
KUBECONFIG=/path/to/isolated-kubeconfig /tmp/runpod-vk \
  --host=HOST --port=PORT --key=/path/to/key \
  --known-hosts=/path/to/pinned-known-hosts \
  --script=/tmp/gradiated-vk-TRIAL/remote.py
```

Apply `smoke.yaml`, wait for the Deployment to become available, scale from two
to three replicas and back to one, then delete it. Inspect the helper's
`pods/<Pod UID>/stdout.log` files over SSH: each must contain
`VK_READY uid=65534`. Restart the controller while pods are running and verify
that their UIDs and remote PIDs remain unchanged.

During cleanup, keep the controller running until pod deletion completes, and
verify that the remote `pods` directory is empty. Then stop the controller,
remove only the trial directory, and remove the local control-plane container.
Do not run this test against allocated model GPUs or production EKS.

For GPU discovery on an idle four-GPU host, restart the controller with
`--gpu-smoke-count=4` and apply `gpu-smoke.yaml`. This schedules one two-GPU
pod and two one-GPU pods on the same virtual node. The helper assigns distinct
GPU UUIDs under a file lock and passes them through `CUDA_VISIBLE_DEVICES`.
Each process initializes the CUDA driver and checks its visible device count;
it does not allocate model weights, execute kernels or test tensor parallelism.
Scale `single-gpu-smoke` to three replicas: the extra replica must stay Pending
with `Insufficient nvidia.com/gpu`. Delete the deployments and verify that no
remote workload state remains, apart from the helper's lock file.

## What remains before this could replace Nomad

- GPU inventory and allocation with reservation coordination against Nomad
  during migration. The discovery test coordinates only its own claims; Nomad
  does not know about them. `CUDA_VISIBLE_DEVICES` alone is not a security
  boundary between arbitrary workloads. The GPU smoke is not a model-serving
  or physical device-isolation qualification.
- Executing our pinned runtime bundles, with separate workload identities,
  resource enforcement and reliable supervision. Conventional containerd/CNI
  workers cannot simply be installed inside the current constrained containers.
- Host and process recovery. This prototype uses Virtual Kubelet's naive node
  heartbeat, so node Ready does not prove SSH or workload health. It does not
  restart crashed processes or implement Kubernetes restart policies.
- Serving endpoints and private reporting over Tailscale. There are no pod IPs,
  Service routing, DNS, volume mounts or network-policy semantics in this test.
- SDK qualification before routing, model warmup, stream draining and rollback,
  including the shared spare-GPU budget across models.
- Authenticated logs/exec endpoints, metrics and restricted controller RBAC.
  The high-level Virtual Kubelet constructor watches Secrets and ConfigMaps;
  that default must be narrowed before connecting to EKS. This prototype reads
  the original pod spec before execution and rejects explicit environments,
  preventing resolved environment values from being transferred to RunPod.
- A dedicated restricted host-management credential. The prototype uses an
  existing administrative SSH key; a production controller must have only the
  host operations it needs, rather than general root shell access.

Normal Kubernetes controllers can manage the virtual pods, but supported pod
execution semantics depend on the provider. This experiment tests that boundary;
it does not establish that a production adapter is cheaper to maintain than
Nomad.
