# Existing-host enrollment tools

This archive extracts the launcher, downloader, archive extractor, and Desmond
binaries from the exact pinned Nomad base used by model releases. It supports the
one-time enrollment of an existing Ubuntu 24.04 x86-64 host without resetting its
container or stopping GPU processes. Newly registered hosts already contain these
tools in their base image.

The installer requires root, the existing runtime/downloader/Desmond accounts,
the existing serving token, and a private artifact-reader environment file. It
checks shared-library compatibility before replacing binaries atomically, restricts
artifact credentials to the downloader, and creates the host-proxy authorization
file for Desmond. It preserves the existing base ID and node metadata and does
not start a model job. Activate the new base ID only with the corresponding Git
job migration, after verifying host compatibility.

The bundle's `verify` target installs twice in a disposable container and checks
the downloader credential permissions and installed binaries. Before enrolling a
legacy host, preserve its existing runtime for rollback and qualify the new model
bundle on the actual GPU before considering the migration complete.

For a new idle RunPod host running a provider image, use
`tools/nomad/install-existing-host.py` with the configured Nomad base inputs tag,
its verified ECR digest, and pinned SSH credentials. Install the base image's
Ubuntu runtime libraries first. The command copies only host tools and config;
it preserves the provider image, SSH access, model cache and GPU reservation.
It refuses enrolled hosts and running Nomad agents. Enrollment verifies the
installed source image and file hashes over pinned SSH before issuing bootstrap
credentials. Register each physical host once; Nomad jobs reserve individual
GPU UUIDs using their device count, so 1-, 2- and 4-GPU jobs can share an 8-GPU
host when CPU and RAM also fit.
