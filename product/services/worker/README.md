# Worker

This TypeScript deployment runs background control-plane work. One loop reads
terminal generation events from Valkey and writes them to ClickHouse. It
acknowledges each event only after ClickHouse confirms the insert.

A separate loop settles eligible five-minute ClickHouse usage slots into
PostgreSQL. One worker replica holds a PostgreSQL advisory lock. The other
replica stays ready and takes control if the leader loses its database session.
The settlement source ID makes each organization and slot idempotent.

The PostgreSQL-to-Valkey reconciliation loop is not implemented yet. The
worker exposes no HTTP service.

## Stream contract

The worker reads `generation-settled:{settlement-0}`. Each stream entry must
have exactly these two fields:

- `generation_id`: the generation UUID.
- `properties`: the JSON form of `GenerationProperties` without `settlement`.

The worker derives `settlement.slot_id` from the stream entry ID. It rejects an
entry that has missing fields, additional fields, or an invalid properties
document. It does not acknowledge a rejected entry.
