# Task: Grad effort/speed and curated provider lanes

## Outcome

The product architecture supports two deliberately connected paths: provider-qualified direct model access for easy migration, and first-party `grad/<effort>/<speed>` products served on owned inference with evidence-backed workload migration recommendations.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/4
- owner: Codex
- created/started: 2026-07-13
- scope: `product/docs/**`, `product/README.md`, `product/HANDOFF.md`, `product/AGENTS.md`, `infra/README.md`, `infra/docs/**`, `docs/ARCHITECTURE.md`, `docs/decisions/**`, and this packet
- excluded: `research/**`, product/infra code, credentials, provider calls, authenticated provider accounts, commits, pushes
- dependency: completed issue #3 product architecture and ADR-0002

## Contract

- user value: existing provider users can change only base URL/key while retaining an explicit provider/model, then receive trustworthy suggestions for lower-cost/faster first-party Grad inference.
- inputs: provider-qualified model request or first-party Grad effort/speed ID, workspace policy, capabilities, privacy, service constraints, and safe workload metadata.
- outputs: deterministic model/route decision, fixed published pricing, actual model/provider disclosure, usage evidence, and optional migration recommendation with confidence/reason/verification path.
- failures: unsupported providers/models/capabilities fail explicitly; direct-provider pins never cross providers or model families; Grad releases never leave owned inference unless a separately named compatibility policy says so; recommendations never auto-migrate traffic.
- persistence/privacy: Product Intelligence retains bounded encrypted payload traces by default for customer features; Private/No Retention is a stricter workspace/request mode; retention does not grant training rights. PostgreSQL owns authorization/tombstones/key state, S3 owns encrypted payloads, and ClickHouse Cloud owns only content-free replayable analytics.
- acceptance: update model taxonomy/names, provider selection syntax, route/data contracts, billing, UX, workload recommendation architecture, ClickHouse/PostgreSQL/S3 trace storage and deletion, PBT/CI, integrations, ADR, delegation plan, and handoff without weakening prior invariants.
- verification: `git diff --check`, DevEx check, local Markdown links, terminology consistency search.
- budget/timeout: $0, documentation only, current turn.
- rollback: revert only paths listed in scope and preserve unrelated `research/**` work.

## Plan

1. Define direct-provider and first-party Grad model identity/taxonomy.
2. Define routing, pricing, privacy-safe traces, and recommendation lifecycle.
3. Adapt all architecture, API, UX, testing, integration, and delegation documents.
4. Verify, update handoff/ADR/task packet, and close issue.

## Result

- status: complete
- delivered: curated direct-provider and `grad/<effort>/<speed>` identity/release contracts; default Product Intelligence retention and no-retain override; workload recommendation/experiment authority; full product/API/billing/security/test/integration/delegation architecture; AWS/EKS/Terraform/Helm/KEDA/local/CI plan; ClickHouse Cloud/PostgreSQL/S3 trace split with ADR-0004 and a source-backed falsification brief.
- verification: `git diff --check`; `python3 tools/devex/check.py`; local Markdown link resolver across 42 product/infra/architecture/task files; terminology search for superseded no-retention and PostgreSQL-only analytics language.
- evidence: current ClickHouse official documentation was retrieved 2026-07-13 and recorded in `product/docs/CLICKHOUSE_TRACE_ANALYTICS_DECISION.md`; all managed capability claims remain vendor-reported and no provider/ClickHouse/AWS request was made.
- limitations: no code or infrastructure exists; provider compatibility, Grad effort/speed monotonicity, recommendation accuracy, ClickHouse tier/cost/query latency/delete/restore behavior and legal/security defaults remain measured implementation gates. ClickHouse has an explicit Aurora-only launch fallback if the bounded spike fails.
- spend: $0.
- next action: delegate product WP-00 and infrastructure I-00 first; I-04B may build the local ClickHouse harness in parallel but cannot create a paid service before account/tier/region/budget/encryption authority is supplied.
