# Runtime bundle launcher

Status: local prototype. No published bundle or deployment integration yet.

`runtime-launch` is a C++ executable for trusted serving runtimes. Nomad calls
it with `raw_exec`. It verifies a tar archive, extracts it into a cache directory
named by its SHA-256 digest, and supervises the bundle entrypoint.
It does not install packages into the base or start a container.

## Bundle contract

The archive contains:

- `base-id`: one line matching `/etc/gradiated/base-id` in the provider image.
- `entrypoint`: an executable regular file.
- The runtime environment and its model-specific launch code.

The base ID identifies the system dependency contract, including OS, CPU
architecture, Python ABI, and required system libraries. Assign a new ID for
incompatible changes. The base image must also contain the launcher, its linked
libraries, CA certificates, Nomad, and the qualified GPU device plugin.

The bundle entrypoint uses `GRADIATED_RUNTIME_ROOT` to find its own files. Use
its interpreter explicitly rather than a console script with an old absolute
shebang. The model launch code pins the checkpoint revision and serving flags.
Keep checkpoint weights in a separate persistent cache.

```sh
runtime-launch --bundle https://artifacts.example/runtime.tar.gz \
  --sha256 <64-character-digest> --cache /workspace/gradiated/runtimes
```

`--archive PATH` uses an existing archive for local tests or staging. Both
sources require a checksum. HTTPS redirects stay on HTTPS. Download limits
are 10 minutes and 20 GiB. Expanded file sizes are limited to 40 GiB.

The launcher serializes extraction per digest and publishes the extracted
directory with an atomic rename. It checks the base ID and entrypoint before
publication. Cache hits skip the download. Cache directories must be private
to the trusted runtime user; this is not a hostile-code sandbox. Cached runtime
files are not rehashed on every launch. Do not mutate published bundles.

A normal error removes staging files. Forced termination can leave a
`*.partial.*` directory; it is never used as a completed cache entry. Cache
retention and prefetch are not implemented yet.

## Nomad integration

The candidate job is `../nomad/jobs/deepseek-v4-1-flash.nomad.hcl`. Its bundle
URL, checksum, base ID, CPU MHz, and memory MiB are required inputs. No resource
sizing or release digest is guessed. Set client metadata `runtime_base_id` to
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
minutes, including up to 10 minutes for the runtime download. Tune this with
measured cold-start data before deployment.

CI builds a versioned runtime bundle separately from the base image. A future
release step will update the job's bundle digest and submit it. This prototype
does not add that release step or change any provider pod.

## Verification

Run the Linux fixture tests:

```sh
docker build -f product/inference/runtime-launcher/tests/Dockerfile \
  product/inference/runtime-launcher
```

These tests cover launch arguments, cache reuse, checksum failure, base
mismatch, archive traversal, HTTPS certificate checks, and writes through
archive symlinks. Process tests cover ordinary and double-forked descendants,
runtime exit, runtime crash, and children that ignore SIGTERM. They check that
unrelated processes remain alive and that the runtime exit status is retained.

Live test: run `../nomad/tests/qualify-raw-exec.sh` with this source directory
as its first argument on the selected Runpod pod, under a 240-second timeout.
It compiles a test adapter around the same supervisor implementation. It does
not install the launcher or change the existing serving processes.

The 25-second grace must be shorter than Nomad's task kill timeout. The
supervisor cannot guarantee cleanup if it is itself killed with SIGKILL, if
the client dies, or if a process remains stuck in an uninterruptible kernel
wait. These cases still require node fencing before replacement. This is
process lifecycle management, not isolation for hostile code.
