# Model runtime releases

On relevant merges, `model-deployment.yml` publishes:

1. The shared Nomad base image to the existing inference ECR repository.
2. One runtime archive per bundle in `release.mjs` to private S3 storage.
3. A release record per bundle with the source revision, base image digest,
   base ID, bundle URL, and SHA-256 digest.

The base contains CUDA, system libraries, Nomad, its NVIDIA device plugin,
the C++ launcher, SSH, and an unprivileged runtime account. It contains no
model weights. A runtime archive contains its own Python, the model's pinned
packages, and its launch scripts: DeepSeek extracts them from the pinned vLLM
distribution, and Kev installs upstream's frozen lock with the source pinned by
commit.

PR checks build the base and verify Python, runtime, and CLI module imports. Merges
publish the base first, then build and verify the bundle against that exact
base digest. Publication never bypasses the verification stage. The CUDA build
requires a GPU even for CLI argument parsing. Full CLI startup, model serving,
and recovery checks therefore run on the GPU qualification node.

## Depot builds

The model checks, runtime publication, shared image builds, and launcher tests
use Depot remote container builders. These jobs run on `depot-ubuntu-24.04`.
The same `DEPOT_PROJECT_ID` repository variable selects the persistent build
cache for PR and release builds. No explicit Docker cache export is required.

Before merging this setup:

1. Enable Depot GitHub Actions runners for `Gradiated/gradiated`.
2. Create a Depot container-build project with enough disk for the CUDA base,
   extracted Python dependencies, and archive. The extracted dependencies are
   about 17 GiB; the archive is about 6.8 GB, before base layers and cache history.
3. Add a GitHub trust relationship for this repository in the Depot project.
   Permit the intended PR and production workflows. This repository uses
   customized OIDC subjects; verify that the trust matches the issued claims.
4. Set the GitHub repository variable `DEPOT_PROJECT_ID` to that project ID.

GitHub OIDC authenticates the builder. Existing AWS OIDC and ECR login steps
still control release publication. Images stay in private ECR; runtime archives
stay in private S3. The builder receives build inputs and registry access for
these builds. It does not receive model weights or the GPU client's credentials.

Dependency extraction is a separate Docker layer from model launch files.
Changing a launch script reuses extraction, but still creates the final archive
and verifies it against the selected base. Changing vLLM rebuilds dependencies.
A warm build still exports the archive to the runner and uploads it to S3.
The first build is cold. No measured Depot speedup is claimed yet.

After setup, compare a cold PR build, an unchanged rebuild, and a launch-script
change. Check that dependency extraction is cached on the last two. Check a
main release separately: its verification uses the published base digest.
Confirm that its release record and S3 archive checksum still match.

References: [Depot GitHub Actions integration](https://depot.dev/docs/container-builds/integrations/github-actions)
and [Depot runners](https://depot.dev/docs/github-actions/overview).

## Change detection

Pull requests build and verify only the bundles whose inputs changed; base and
shared packaging changes verify every bundle. Documentation, test-only changes, and
unrelated release tooling run the quick checks without rebuilding the runtime.
The comparison covers the full pull request. New pushes cancel older PR runs;
production releases are not cancelled. Depot keeps the Docker build layers between runs.

Image inputs use the existing image catalog. A changed base Dockerfile,
launcher, or base configuration produces a new base digest. Bundle inputs
include that digest, its Dockerfile and packaging scripts, the model launch
script, and the release tooling. An unchanged input digest reuses the release
record. The record retains the source revision of the original build.

Archives use content-addressed keys. Records use build-input keys. Uploads
finish before their release record is published. No mutable `latest` URL is
used by a serving job.

## Storage setup

Terraform's registry module owns the private artifact bucket. The deployment
role can upload and read its objects. When a merge also changes Terraform inputs, runtime publication waits for
the Terraform workflow for that commit to succeed. The existing Terraform
workflow applies the private bucket and deployment-IAM changes on merge.
A failed infrastructure run prevents runtime publication.

During client enrollment, install the read-only S3 environment file at
`/etc/gradiated/artifact.env`, owned by `downloader:downloader` (UID 10003)
with mode `0400`. Grant only `s3:GetObject` on the bucket's `bundles/*` prefix.
The Nomad pre-start task runs `s5cmd` with eight parallel ranges, checks SHA-256,
and extracts the trusted release into the shared allocation directory. It
publishes the directory only after extraction succeeds. The model task cannot
start if download or verification fails. Process restarts reuse this directory;
a replacement allocation downloads its own copy.

Do not put credentials in the image, job, bundle, or model environment. The
`runtime` user cannot read the downloader credential file. The `downloader`
user cannot read Nomad TLS keys. Terraform creates a read-only IAM user for
each configured instance. Access keys are created outside Terraform and stored
in the instance secret; no key values enter Terraform state.

When enrolling a node with base v2, move the credentials from the old
`/etc/nomad/artifact.env` location and remove that old file. The Nomad agent
no longer needs S3 credentials. Install the new base before submitting the
pre-start job; older bases lack the downloader user and tools.

## GPU rollout

A successful publication triggers the Nomad deployment, which gives each job
named after a bundle the `bundle_url`, `bundle_sha256` and `base_id` from its
release record for that commit. A job without a vars file is never submitted.
CPU, memory, and runtime disk reservations must come from the measured deployment.

A changed bundle digest triggers a destructive allocation update when the
new job is submitted. The job uses `max_parallel = 1` and health checks to
gate further replacements. With one four-GPU replica and no spare capacity,
the old replica stops before the new one starts. With multiple replicas,
Nomad replaces one allocation at a time. This is a rollout policy, not a
Kubernetes PDB.

Changing the provider base image is a node maintenance operation. Nomad does
not replace a Runpod pod image. Drain the client, update its base, enroll it
again, and qualify it before placing workloads. The base-ID constraint blocks
a runtime from landing on an incompatible client. Change the base ID whenever
the system dependency contract changes.

References: [Nomad update policy](https://developer.hashicorp.com/nomad/docs/job-specification/update)
and [artifact downloads](https://developer.hashicorp.com/nomad/docs/job-specification/artifact).
