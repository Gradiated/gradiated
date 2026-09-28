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
