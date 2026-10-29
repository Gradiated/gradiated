# Runtime bundle launcher

`runtime-launch` is a small C++ executable for trusted serving runtimes.
The GPU host agent stages pinned archives through private short-lived download
grants. The downloader verifies SHA-256 and extracts a shared, read-only bundle.
The launcher checks base compatibility and supervises the entrypoint. It does
not install packages or start a container.

## Bundle contract

The archive contains:

- `base-id`: one line matching `/etc/gradiated/base-id` in the provider image.
- `entrypoint`: an executable regular file.
- The runtime environment and its model-specific launch code.

`runtime-launch` and `desmondd` are supplied by the verified host bundle. Host
updates preserve existing runtime processes. Install a compatible host bundle
before deploying model archives without a bundled launcher.

The base ID identifies the system dependency contract, including OS, CPU
architecture, Python ABI, and required system libraries. Assign a new ID for
incompatible changes. The base image supplies the C++
standard library and CA certificates. The host agent assigns exclusive GPU UUIDs.

The bundle entrypoint uses `GRADIATED_RUNTIME_ROOT` to find its own files. Use
its interpreter explicitly rather than a console script with an old absolute
shebang. The model launch code pins the checkpoint revision and serving flags.

```sh
runtime-launch /path/to/extracted/runtime -- optional-entrypoint-argument
```

The GPU host agent downloads and verifies each pinned bundle before starting
its launcher. The launcher receives the extracted bundle directory as its first
argument. A failed download or checksum check prevents startup.

The host stages verified bundles under `/var/lib/gradiated-kubelet/bundles/<SHA256>`.
Pods using the same digest share those executable files; each pod has its own
scratch directory, training data and LoRA cache. Model processes cannot modify
the bundle. After processes stop, pod deletion removes training data and adapter
caches while retaining diagnostic logs.

The downloader keeps at most four compressed runtime archives under
`/var/cache/gradiated/runtime-bundles`, owned by `downloader` with mode `0700`.
It verifies SHA-256 before extraction. A host-wide cache lock protects downloads,
verification and eviction. Budget disk space for both the archive cache and the
extracted bundles. This cache does not hold initialized GPU state or shorten the
request drain.

Measured production bundle downloads took 473 seconds for GLM and 995 seconds
for DeepSeek; extraction took 18 and 39 seconds respectively. An isolated GLM test on an idle B300 host measured 367 seconds for cold bundle
readiness and 19 seconds for each of two cached extractions, including a fresh
SHA-256 check. The archive cache avoids repeated transfers for unchanged bundles. New bundle digests still need
one download per host. It does not cache initialized GPU state or shorten the
11-minute request drain. Keep inference model weights in
`/home/runtime/.cache/huggingface`, on node-local disk outside the allocation.
All three inference jobs share this Hugging Face cache within each host and pin
model/tokenizer revisions. Missing files download automatically; completed blobs
are reused across allocations, models and revisions. Kernel caches remain under
`/home/runtime/.cache`. Runtime archives, weights and compiled kernels are all
disposable; a reset can wipe them and startup rebuilds them. Neither `/workspace`
network storage nor `/dev/shm` is required for inference checkpoint storage.
Budget local disk for weights, retained revisions, archives and allocation files.
No prewarming, copied checkpoints or manual cache preparation is required.
Hugging Face retains downloaded revisions; only runtime archives have bounded
automatic eviction. Treat retained files as disposable acceleration, never as
the only copy of an artifact.

`fetch-runtime` ships in the host bundle and runs from the active bundle's
directory, so it changes with a host bundle release. The GPU base image creates
its cache, `/var/cache/gradiated/runtime-bundles`, owned by `downloader`.

The downloader accepts only content-addressed S3 release URLs. It verifies
the digest before using `bsdtar` to extract the trusted archive.
Eight ranges share one staging file and a twenty-minute download deadline.
The artifact bucket enables S3 Transfer Acceleration. The helper replaces the
regional endpoint with `s3-accelerate.amazonaws.com` when downloading; pinned
release URLs and bundle digests stay unchanged, so enabling this does not require
a serving rollout. Older helpers can still use the regional endpoint. Transfer
Acceleration adds AWS data-transfer charges. An isolated 3.8 GB GLM archive
comparison on the serving B300 host measured a verified accelerated download in
9.8 seconds; the preceding regional download exceeded its ten-minute test limit.
Transient size-probe and range failures retry within that deadline; each range
resumes from its written prefix. Startup logs show the download, checksum and
extraction phases. Compatible host-tool updates install the helper and curl
without restarting running workloads or changing provider images.
The job requires `runtime_disk_mb`; include space for the compressed archive,
extracted runtime, and logs. Measure this for each release.

## Exit status

| Status            | Cause                                                                       |
| ----------------- | --------------------------------------------------------------------------- |
| Runtime exit code | The runtime exits normally.                                                 |
| 128 + N           | The runtime dies from signal N.                                             |
| 128 + N           | The launcher receives shutdown signal N. This overrides the runtime status. |
| 127               | The entrypoint cannot be executed. Stderr names the path and the error.     |
| 126               | The runtime process cannot be prepared.                                     |
| 1                 | A validation or setup error occurs before the runtime starts.               |

## Signals and cleanup

The launcher starts a guardian that is a Linux child subreaper in a separate
session. The host agent can kill the launcher process group during cleanup without
killing the guardian. The guardian starts the entrypoint in another session
and adopts orphaned descendants. Normal
shutdown signals pass through the launcher to the guardian. If the launcher
is killed, a kernel parent-death notification makes the guardian immediately
kill and reap the remaining runtime tree, including detached workers.

- The first SIGTERM, SIGINT, or SIGHUP goes unchanged to direct and adopted
  children.
- When the runtime exits, the remaining descendants get SIGTERM.
- SIGKILL follows after the grace period. `default_shutdown_grace` in
  `supervise.h` sets it to 25 seconds.
- The launcher returns only when no descendants remain.
- The launcher resets inherited ignored shutdown signals and SIGCHLD. It
  also unblocks the shutdown signals in the runtime.

The supervisor cannot guarantee cleanup in these cases:

- The guardian itself gets SIGKILL, or the entire process tree is killed.
- The host agent cannot establish that the process tree stopped.
- A process stays in an uninterruptible kernel wait.

Fence the node before you replace it in these cases. This is process lifecycle
management. It does not isolate hostile code.

## Runtime liveness

Serving jobs set `RUNTIME_STARTUP_TIMEOUT_SECONDS` and `RUNTIME_PORT`. The launcher
checks `http://127.0.0.1:$RUNTIME_PORT/health` every five seconds, with a two-second
request timeout. Until the first healthy response, it allows the configured cold
start (Kev 30 minutes, GLM 60 minutes, DeepSeek 90 minutes). Once healthy, three
consecutive failures kill and reap the whole runtime tree immediately and return
a failed task exit; the host agent's bounded restart policy starts a fresh serving process. A startup that
never becomes healthy also exits when its deadline expires.

The state lives in the launcher process and resets only with the runtime task.
Kubernetes readiness updates cannot reopen the startup grace. Normal shutdown signals still use the 25-second cleanup grace;
rollouts still drain existing requests before signaling. Jobs without the startup
timeout retain process supervision without liveness polling.

## Kubernetes integration

The [GPU host agent](../gpu/host-agent.py) owns process supervision, GPU UUID
claims, CPU and memory cgroups, and the loopback inference proxy. Kubernetes
owns placement and pod lifecycle; Argo Rollouts owns canary qualification and
promotion. The worker derives deployment rows from Kubernetes pod UIDs.

Bundles come from the pinned [runtime catalogue](../gpu/runtimes.json). The host
agent stages and verifies new catalogue entries before launching them. Temporary
staging failures leave pods Pending. The host supervisor preserves model
processes across management-agent restarts.

Desmond observes each serving runtime and posts status through the private
localhost control bridge. It cannot access the database or Kubernetes API.
Readiness requires a healthy runtime and SDK qualification of the current
process identity. A restarted process must qualify again.

On pod deletion, the host agent withdraws new requests, drains qualified serving
processes for 660 seconds, then stops their process trees and releases GPU claims.
Training Jobs use their own lease and cancellation protocol without that serving
drain. Provider resets lose host-local state; do not reset an allocated GPU.

## Verification

The launcher builds only on Linux. The Docker test image is the supported
check. It runs CTest, ShellCheck, clang-format, and shfmt. It also checks
pre-start ordering, checksum rejection, and download failure cleanup.

```sh
docker build -f product/inference/runtime-launcher/tests/Dockerfile \
  --target tests product/inference
```

For a production build, configure CMake with `-DBUILD_TESTING=OFF`.
The installed launcher has no test-tool dependency.

CTest reports each case separately:

- `launcher.*` checks literal launch arguments and the canonical runtime root.
  It rejects missing, mismatched, blank, or oversized base IDs, invalid
  entrypoints, and bad arguments. Each rejection test checks the error message.
  `launcher.bad-interpreter` checks status 127 and its message.
- `cleanup.*` starts ordinary and double-forked descendants. It covers stop,
  interrupt, hangup, runtime exit, and runtime crash. Each descendant must
  receive the forwarded signal. Cleanup must finish in less than five seconds.
  Unrelated processes must stay alive, and the exit status must be correct.
- `cleanup.ignored-*` and `cleanup.blocked-stop` start the launcher with
  inherited ignored or blocked signals. They check the same results.
- `cleanup.launcher-killed` kills the launcher with SIGKILL while ordinary and
  detached workers are alive, including a worker that ignores SIGTERM. It
  requires every descendant to disappear within five seconds.
- `cleanup.stubborn` runs the supervise adapter with a 2-second grace. A
  detached child ignores SIGTERM. The test checks that SIGKILL waits for the
  grace period and that no descendant remains.
  The Docker checks also run the private bundle downloader tests with synthetic
  artifact grants. Live qualification must check real SDK requests, recovery after
  a model-process crash, rollout abort and rollback, and isolation from database
  and Kubernetes API endpoints. The tests do not require a running GPU host agent.

## Why the small supervisor remains

Tini forwards signals to a process group and reaps children. It does not stop
a worker that starts a separate session when the main child of Tini exits.
A local comparison used Tini 0.19.0 with `-s -g` and the
`tests/process-tree.cpp` fixture in `stop` mode. The detached child stayed
alive after Tini exited. The C++ supervisor passes that fixture, and it kills
stubborn processes after the grace period. The supervisor needs no
third-party C++ libraries.
