# Runtime bundle launcher

Status: published runtime bundles; live serving qualification is in progress.

`runtime-launch` is a small C++ executable for trusted serving runtimes.
A Nomad pre-start task downloads the pinned archive with `s5cmd`, checks its
SHA-256 digest, and extracts it into the shared allocation directory. It runs
as `downloader`, with read-only S3 credentials that the model user cannot read.
The launcher checks base compatibility and supervises the entrypoint.
It does not download files, install packages, or start a container.

## Bundle contract

The archive contains:

- `base-id`: one line matching `/etc/gradiated/base-id` in the provider image.
- `entrypoint`: an executable regular file.
- The runtime environment and its model-specific launch code.
- `runtime-launch` and `desmondd`, built from the same pinned base, so supervisor
  and readiness fixes roll out with the model without updating a GPU host.

The base ID identifies the system dependency contract, including OS, CPU
architecture, Python ABI, and required system libraries. Assign a new ID for
incompatible changes. The base image must also contain the launcher, the C++
standard library, CA certificates, Nomad, and the qualified GPU device plugin.

The bundle entrypoint uses `GRADIATED_RUNTIME_ROOT` to find its own files. Use
its interpreter explicitly rather than a console script with an old absolute
shebang. The model launch code pins the checkpoint revision and serving flags.

```sh
runtime-launch /path/to/extracted/runtime -- optional-entrypoint-argument
```

Nomad extracts the archive into `local/runtime`. The job passes its absolute
path through `NOMAD_ALLOC_DIR`. A failed download or checksum check prevents
task startup. Direct local launches expect an already verified directory.

Runtime files belong to each allocation. A new allocation downloads its own
copy. There is no shared runtime cache, prefetch service, or cache lock.
Keep model weights in `/workspace/gradiated/model-cache`, outside the allocation.
Add a shared runtime cache only if measured download time requires it.

The downloader accepts only content-addressed S3 release URLs. It verifies
the digest before using `bsdtar` to extract the trusted archive. Nomad's native
artifact size and file-count limits do not apply to this pre-start task.
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

The launcher starts a guardian that is a Linux child subreaper. The guardian
starts the entrypoint in a new session and adopts orphaned descendants. Normal
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
- The Nomad client dies.
- A process stays in an uninterruptible kernel wait.

Fence the node before you replace it in these cases. This is process lifecycle
management. It does not isolate hostile code.

## Nomad integration

The model jobs in `../nomad/jobs/` own task layout, resources, health checks,
canaries and shutdown timing. A pre-start task verifies and extracts the runtime
bundle. The serving task runs that bundle's launcher with the allocation's
runtime directory. The task `kill_timeout` must exceed the supervisor's 25-second
shutdown grace. Its eleven-minute `shutdown_delay` lets existing requests finish
after deregistration and before the supervisor receives SIGTERM.

Git pins each job and its runtime inputs. The deployment workflow resolves the
published content-addressed release, supplies its URL, checksum and compatible
base ID, and waits for the resulting Nomad deployment. Publish new bundle
capabilities before a job starts using them. Missing compatible canary capacity
leaves the previous allocations serving until placement succeeds or the
rollout's deadline causes rollback.

Initial instance registration installs the client certificate, artifact reader
and private Desmond credentials. Serving tasks cannot read those credentials.
The `host-proxy` system job publishes allocation-aware routes through the host's
port 8888; it authenticates requests and strips the bearer token before forwarding
them to loopback runtimes. The worker derives deployment rows from Nomad, and
Desmond reports readiness. Do not create deployment rows by hand.

Qualify process cleanup with real runtime crashes and restarts, then check a
real SDK inference request through the gateway. A passing runtime health check
alone does not prove model identity or end-to-end routing.

## Ingress readiness

For Nomad host-proxy jobs, set `DESMOND_INGRESS_PORT=8888` on the bundled
Desmond observer. It checks `/alloc/<deployment-id>/health` on loopback through
the host proxy, using the private runtime access token. Readiness therefore
requires both a healthy runtime and an installed allocation route. Metrics still
come directly from the runtime. The bearer token is never included in logs.

Start this observer as a post-start sidecar: the pre-start downloader must finish
before the bundle's executable is available. The observer does not restart the
runtime if ingress or status ingestion becomes unavailable. Publish bundles with
this capability before switching jobs to the new executable and environment value.

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
- `nomad.artifact` runs a local Nomad 2.0.6 agent without a GPU. It checks
  pre-start ordering and checksum rejection with a local copy in place of S3.
  Real S3 transfer speed and credential isolation require the live provider
  test.

The Nomad test runs only in the disposable container. It replaces
`/usr/local/bin/s5cmd`, writes `/etc/gradiated/artifact.env`, and starts a
temporary agent as `nobody`.

Live test: run `../nomad/tests/qualify-raw-exec.sh` on the selected Runpod
pod, under a 240-second timeout. Give this source directory as its first
argument. The script compiles `tests/supervise-main.cpp` around the same
supervisor and uses the default shutdown grace. It does not install the
launcher or change the serving processes.

## Why the small supervisor remains

Tini forwards signals to a process group and reaps children. It does not stop
a worker that starts a separate session when the main child of Tini exits.
A local comparison used Tini 0.19.0 with `-s -g` and the
`tests/process-tree.cpp` fixture in `stop` mode. The detached child stayed
alive after Tini exited. The C++ supervisor passes that fixture, and it kills
stubborn processes after the grace period. The supervisor needs no
third-party C++ libraries.
