# Worker

The background worker: it ingests finalized generations from Valkey into ClickHouse, settles them into PostgreSQL and reconciles model deployments from Nomad.

## entrances

- generation ingestion: the worker reads finalized generation events that the gateway appends to the Valkey stream
  handler: runGenerationIngestionLoop in src/generation-ingestion-loop.ts
  trust: serving-state
- settlement: the worker posts each closed settlement slot to PostgreSQL
  handler: runGenerationSettlementLoop in src/settlement-loop.ts
  trust: serving-state
- deployment reconciliation: the worker derives model deployments from the allocations Nomad reports
  handler: reconcileDeployments in src/deployment-reconciliation.ts
  trust: cluster

## invariants
