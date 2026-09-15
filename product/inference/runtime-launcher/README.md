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

The base ID identifies the system dependency contract, including OS, CPU
architecture, Python ABI, and required system libraries. Assign a new ID for
incompatible changes. The base image must also contain the launcher, the C++
standard library, CA certificates, Nomad, and the qualified GPU device plugin.

The bundle entrypoint uses `GRADIATED_RUNTIME_ROOT` to find its own files. Use
its interpreter explicitly rather than a console script with an old absolute
shebang. The model launch code pins the checkpoint revision and serving flags.
Keep checkpoint weights in a separate persistent cache.

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

## Nomad integration

The candidate job is `../nomad/jobs/deepseek-v4-1-flash.nomad.hcl`. Its bundle
URL, checksum, base ID, CPU MHz, memory MiB, and runtime disk MiB are required
inputs. No resource sizing or release digest is guessed. Set client metadata `runtime_base_id` to
the ID installed in the provider image. Configure a `loopback` host network.

Before submitting this job, qualify the following on the actual provider:

1. GPU reservation bookkeeping passed a live Runpod test with Nomad 2.0.6
   and NVIDIA plugin 1.1.0. Two allocations received disjoint GPU pairs.
   This does not enforce device isolation from other processes.
2. The bundle entrypoint maps assigned device UUIDs to `CUDA_VISIBLE_DEVICES`.
   A visibility mask is not device isolation.
3. The runtime user cannot read the Nomad client key.
4. Synthetic process-tree cleanup now passes locally and on a live Nomad
   client. The launcher acts as a Linux child subreaper. On shutdown or runtime
   exit, it terminates descendants, escalates to SIGKILL after 25 seconds, and
   reaps them before returning. The live test included detached processes
   that ignored SIGTERM. A real vLLM stop/restart test remains required.
5. Set the client's maximum kill timeout to at least 60 seconds.
6. Confirm checkpoint identity and a small inference request before exposing
   traffic. The Nomad health check alone does not establish model identity.

The job reserves four B300 devices on one client. No host-loss replacement is
requested automatically. The localhost service is for health checks; it does
not register an endpoint with the Gradiated gateway. Cold-start grace is 65
minutes after the model task starts. Bundle download runs before that task
starts and has a 20-minute limit; extraction has a 10-minute limit. Tune these
with measured startup data before deployment.

CI builds a versioned runtime bundle separately from the base image. A future
release step will update the job's bundle digest and submit it. This prototype
does not add that release step or change any provider pod.

## Verification

The Docker test image runs CTest, ShellCheck, clang-format, and shfmt. It also
checks pre-start ordering, checksum rejection, and download failure cleanup.
CTest reports each launcher and cleanup case separately. The integration test
runs only in this disposable container because it creates a local CA and
starts a temporary Nomad agent.

Run the checks:

```sh
docker build -f product/inference/runtime-launcher/tests/Dockerfile \
  product/inference
```

For a production build, configure CMake with `-DBUILD_TESTING=OFF`.
The installed launcher has no test-tool dependency.

These tests cover literal launch arguments, missing or mismatched base IDs,
and invalid entrypoints. Process tests cover ordinary and double-forked
descendants,
runtime exit, runtime crash, and children that ignore SIGTERM. They check that
unrelated processes remain alive and that the runtime exit status is retained.

A local Nomad 2.0.6 fixture checks pre-start ordering and checksum rejection,
using a local copy in place of S3. It runs without a GPU. Real S3 transfer speed
and credential isolation require the live provider test.

Live test: run `../nomad/tests/qualify-raw-exec.sh` with this source directory
as its first argument on the selected Runpod pod, under a 240-second timeout.
It compiles a test adapter around the same supervisor implementation. It does
not install the launcher or change the existing serving processes.

The 25-second grace must be shorter than Nomad's task kill timeout. The
supervisor cannot guarantee cleanup if it is itself killed with SIGKILL, if
the client dies, or if a process remains stuck in an uninterruptible kernel
wait. These cases still require node fencing before replacement. This is
process lifecycle management, not isolation for hostile code.

## Why the small supervisor remains

Tini forwards signals to a process group and reaps children. It does not
terminate a worker that starts a separate session when its main child exits.
The local comparison used Tini 0.19.0 with `-s -g` and the same
`tests/process-tree.cpp` fixture in `stop` mode. The detached child remained
alive after Tini exited. The container was removed after the test.
The C++ supervisor passes that fixture, including forced cleanup after its
25-second grace period. Download changes do not affect this process cleanup.
No third-party C++ libraries are needed.
