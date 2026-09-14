# Nomad relay

Small Rust service for the Nomad SSH relay in EKS. Deployment is pending.
It runs beside OpenSSH in one container. It is separate from the inference gateway.

```text
GPU host: Nomad client -> OpenSSH client
                              |
                         SSH connection
                              |
EKS pod:                  nomad-relay + sshd -> private Nomad servers:4647
```

OpenSSH carries Nomad RPC traffic. Nomad mutual TLS authenticates that traffic.
The Rust process manages Linux accounts and public keys and supervises `sshd`.
It does not forward inference requests, runtime status, or application logs.
The production image has no Python dependency.

## Inputs and behavior

Mount `/access/instances.json` read-only. It contains an array of objects with
exactly `instance_id` (UUID) and `public_key` (Ed25519 public key without a comment
or options). An empty array revokes all access. Mount the directory, not a
Kubernetes `subPath`, so ConfigMap updates become visible.

Mount the relay host key at `/host-keys/ssh_host_ed25519_key` read-only.
Clients must pin its public key. Never put private keys in the image or Git.

The service reads the inventory every two seconds. Each instance receives an
account named `ni_` plus the first 24 UUID hex digits. It rejects account-name
collisions and reused public keys. It writes authorized keys by atomic rename.
A removed or changed key closes that account's active SSH connections before
any replacement key is installed. Other instance connections remain open.

Invalid or unreadable inventory stops the relay and closes instance sessions.
SIGTERM and SIGINT also close access. Restart the container after a service
failure. Do not restart the binary in the same container: it rejects existing
accounts. `/run` must be private to this container. Do not share it across replicas.

The container needs root for account creation, OpenSSH privilege separation,
and process termination. It does not need host networking, host PID access,
or privileged container mode. Kubernetes deployment and capability checks remain
pending. Each relay replica must receive the current access inventory. Revocation
latency includes Kubernetes volume propagation, plus the two-second poll interval.

`sshd_config` permits only the three private Nomad RPC destinations. It denies
shells, commands, reverse forwarding, and unrelated destinations.

## Local checks

From the repository root:

```sh
cargo fmt --manifest-path product/services/nomad-relay/Cargo.toml --check
cargo clippy --manifest-path product/services/nomad-relay/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path product/services/nomad-relay/Cargo.toml --locked
docker build --platform linux/amd64 --target integration -t gradiated/nomad-relay:test product/services/nomad-relay
cargo test --manifest-path product/services/nomad-relay/Cargo.toml --test tunnel -- --ignored
docker build --platform linux/amd64 --target production -t gradiated/nomad-relay:local product/services/nomad-relay
```

The Rust integration test runs on the developer machine. Its echo fixture is Rust
and is only in the integration image. Temporary test keys stay outside the repo.
The base images and Cargo dependencies are pinned. Debian packages resolve at
build time; record and deploy the final image digest after qualification.

## Verification record

Local Linux/amd64 Docker verification passed on 2026-09-14. Three Rust unit
tests, formatting, and Clippy passed. Container checks passed for two concurrent
instance tunnels, denied shell access, denied undeclared destinations, active
revocation, unaffected second-instance traffic, denied revoked reconnection,
and shutdown after invalid inventory. Observed revocation took 2.28 seconds
in the final test, including the reconnect check. This is local evidence, not
an EKS latency guarantee. The production image built successfully and contains
neither Python nor the echo fixture.

An initial Debian HTTP package download failed hash verification. HTTPS package
downloads passed with hash and TLS checks enabled. No verification was disabled.
