# Private adapter hosting

The implementation uses pinned runtime bundles, Kubernetes serving Rollouts and
short-lived S3 grants. Adapters load into compatible base replicas; they do not
create one deployment per adapter. PostgreSQL stores immutable adapter identity
and artifact references. Desmond reports runtime and adapter readiness through
the private Tailscale control listener.

The host keeps a bounded adapter cache and removes per-pod cache files after the
workload stops. Root management and local Desmond control credentials protect
privileged host operations; inference traffic uses Tailscale network identity.
GPUs cannot reach PostgreSQL, Valkey or the Kubernetes API.

The current contracts are [adapter serving](TASK_FINE_TUNING_SERVING_CONTRACT.md),
[training runs](TASK_FINE_TUNING_RUN_CONTRACT.md) and
[GPU scheduling](TASK_FINE_TUNING_FLEET_CONTRACT.md).
