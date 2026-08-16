# Worker

This TypeScript deployment will run the three independently supervised loops
defined in `docs/ARCHITECTURE.md`: PostgreSQL-to-Valkey reconciliation, Valkey
generation ingestion into ClickHouse, and ClickHouse-slot settlement into
PostgreSQL. It shares `packages/control`, `packages/contracts` and
`packages/config` with the API but exposes no HTTP service.
