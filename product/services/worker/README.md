# Worker

This TypeScript deployment runs background control-plane work. One loop reads
terminal generation events from Valkey and writes them to ClickHouse. It
acknowledges each event only after ClickHouse confirms the insert.

A separate loop settles eligible five-minute ClickHouse usage slots into
PostgreSQL. One worker replica holds a PostgreSQL advisory lock. The other
replica stays ready and takes control if the leader loses its database session.
The settlement source ID makes each organization and slot idempotent.

A third loop projects current serving state from PostgreSQL into Valkey. It
replays PostgreSQL-originated balance transactions through
an atomic Valkey script. The script applies each transaction ID only once.
Generation settlement transactions are excluded because the gateway already
applied those charges. Both replicas can run this loop safely.

The worker exposes no HTTP service. A complete rebuild after total Valkey loss
remains a controlled maintenance operation. The normal projector does not
overwrite an operational Valkey balance from the PostgreSQL balance.

## Stream contract

The worker reads `generation-settled:{settlement-0}`. Each stream entry must
have exactly these two fields:

- `generation_id`: the generation UUID.
- `properties`: the JSON form of `GenerationProperties` without `settlement`.

The worker derives `settlement.slot_id` from the stream entry ID. It rejects an
entry that has missing fields, additional fields, or an invalid properties
document. It does not acknowledge a rejected entry.
