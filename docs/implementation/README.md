# Startup implementation manual

This directory converts the canonical [system manual](../SYSTEM_MANUAL.md) into implementation contracts for parallel agents.

Read in order:

1. [Document status](DOCUMENT_STATUS.md) — precedence, current blueprints and historical evidence.
2. [Contract catalog](CONTRACT_CATALOG.md) — every cross-package/service interface and compatibility rule.
3. [Physical data model](DATA_MODEL.md) — exact PostgreSQL rows, constraints, indexes and write ownership.
4. [Package boundaries](PACKAGE_BOUNDARIES.md) — source layout, core classes/traits and allowed dependencies.
5. [Path ownership](PATH_OWNERSHIP.md) — mechanically disjoint writable roots for every packet.
6. [Work packages](WORK_PACKAGES.md) — dependencies, steps and packet acceptance.
7. [Verification matrix](VERIFICATION_MATRIX.md) — properties, end-to-end scenarios, SLOs and launch gates.
8. [Operations manual](OPERATIONS_MANUAL.md) — observability, incidents, recovery and rotation.
9. [System diagrams](../SYSTEM_DIAGRAMS.md) — context, sequence, state, deployment and dependency views.

## Agent start protocol

An implementation agent must:

1. identify one unblocked packet ID;
2. verify every dependency commit/contract digest exists on `main`;
3. claim one GitHub issue and repository task packet;
4. reserve exact paths and exclude neighboring/active work;
5. copy the packet outcome, failure behavior and acceptance checks into the issue;
6. implement against checked-in fakes/goldens before external systems;
7. run narrow then required verification;
8. update the nearest handoff/runbook and publish only owned files.

An agent must not add a field, dependency, service or compatibility behavior merely to unblock itself. Missing architecture is reported against the owning packet and represented by a deterministic failing fixture where possible.

## Integrator protocol

One integrator per wave verifies:

- all packet dependencies and generated artifacts match;
- no two packages claim the same authority or write path;
- cross-service fixtures pass from both producer and consumer;
- the capability coverage ledger has no owner/test gap;
- historical documents did not re-enter implementation sources;
- the fake whole-system scenarios for that wave pass;
- handoff paths and GitHub issue states are current.

The integrator may repair documentation/index conflicts but does not silently change a contract owned by another packet.
