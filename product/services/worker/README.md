# Worker

This TypeScript deployment runs background control-plane work. The first
implemented loop reads terminal generation events from Valkey and writes them
to ClickHouse. It acknowledges each event only after ClickHouse confirms the
insert.

The PostgreSQL-to-Valkey reconciliation loop and the ClickHouse-to-PostgreSQL
settlement loop are not implemented yet. The worker exposes no HTTP service.

## Stream contract

The worker reads `generation-settled:{settlement-0}`. Each stream entry must
have exactly these two fields:

- `generation_id`: the generation UUID.
- `properties`: the JSON form of `GenerationProperties` without `settlement`.

The worker derives `settlement.slot_id` from the stream entry ID. It rejects an
entry that has missing fields, additional fields, or an invalid properties
document. It does not acknowledge a rejected entry.
