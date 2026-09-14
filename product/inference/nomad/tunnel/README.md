# Nomad client transport

Status: Rust relay container integration passed locally; EKS deployment pending.

The SSH relay runs in EKS. It is separate from the inference gateway.
Its Rust account reconciler is in `product/services/ssh-relay` and does not run on GPU hosts. GPU hosts use the
OpenSSH client and Nomad client. Custom GPU host-agent code will use C++.
The shell script starts the SSH client; it is not a Python service.

Each GPU host starts client.sh under its host-agent user. An external supervisor
restarts the tunnel with bounded backoff. OpenSSH checks the tunnel server's
pinned host key. Nomad authenticates its own RPC traffic with mutual TLS inside
this connection. No provider IP is part of the host identity.

The three loopback listeners are forwarding endpoints, not Nomad servers.
Server ordinal 0 advertises 127.77.0.1:4647 to clients; ordinals 1 and 2 use
127.77.0.2 and 127.77.0.3. Every GPU client has the same three local mappings.
Server gossip advertises the real EKS pod IP. Nomad 2.0.6 derives server-to-server
RPC from that gossip address, separately from the client RPC advertisement.
Qualify this behavior with the pinned version before rollout.

The SSH relay needs one restricted OS account per approved instance, with
one authorized public key. The ni_ prefix is reserved for these accounts.
The relay must reject accounts not in the approved inventory. No shared host
key or shared instance account is permitted. The service’s sshd_config allows only the three
RPC destinations and prohibits shell sessions and reverse forwarding.

The account reconciler must remove a revoked key and terminate that account's
active SSH processes on every relay replica. Merely rewriting authorized_keys
is insufficient. Relay account reconciliation and active revocation passed local container tests.
EKS deployment and multi-replica revocation checks remain pending.

The relay's host private key and instance private keys stay outside Git.
Only public keys and approved instance identifiers belong in its access inventory.
The host CA private key is never installed here or on the GPU nodes.

This transport does not carry inference back to vLLM or readiness to the API.
Those routes need separate authenticated configuration. Do not add destinations
or reverse forwarding implicitly.
