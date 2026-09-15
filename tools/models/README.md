# Model runtime releases

On relevant merges, `model-deployment.yml` publishes:

1. The shared Nomad base image to the existing inference ECR repository.
2. A DeepSeek runtime archive to private S3 storage.
3. A release record with the source revision, base image digest, base ID,
   bundle URL, and SHA-256 digest.

The base contains CUDA, system libraries, Nomad, its NVIDIA device plugin,
the C++ launcher, SSH, and an unprivileged runtime account. It contains no
model weights. The runtime archive contains Python, the packages from the
pinned vLLM distribution, and the model launch scripts.

PR checks build the base and verify Python, runtime, and CLI module imports. Merges
publish the base first, then build and verify the bundle against that exact
base digest. Publication never bypasses the verification stage. The CUDA build
requires a GPU even for CLI argument parsing. Full CLI startup, model serving,
and recovery checks therefore run on the GPU qualification node.

## Change detection

Pull requests run the full runtime build when base inputs, runtime packaging,
or the DeepSeek launch script change. Documentation, test-only changes, and
unrelated release tooling run the quick checks without rebuilding the runtime.
The comparison covers the full pull request. New pushes cancel older PR runs;
production releases are not cancelled. This does not add a persistent build cache.

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

During client enrollment, supply read-only S3 credentials in the Nomad
agent's private environment. Grant only `s3:GetObject` on the bucket's
`bundles/*` prefix. The client forwards these variables to Nomad's artifact
downloader. Do not put credentials in the image, job, bundle, or runtime user
environment. Terraform creates a separate read-only IAM user for each configured instance.
Access keys are created outside Terraform and stored in the instance secret.
No key values enter Terraform state. The runtime user cannot read the agent
credential files, and Nomad excludes AWS credentials from task environments.

## GPU rollout

Publication and job submission are separate. This workflow does not submit
a serving job before the first GPU qualification. The release record supplies
`bundle_url`, `bundle_sha256`, and `base_id` for that submission. CPU, memory,
and runtime disk reservations must come from the measured deployment.

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
