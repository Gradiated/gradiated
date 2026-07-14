# ADR-0008: REST/OpenAPI control contract, generated MCP and self-service deletion

- Status: accepted
- Date: 2026-07-14
- Supersedes: tRPC control-surface decisions in earlier planning documents

## Decision

Implement the TypeScript control plane as versioned Hono REST under `/api/v1`. Described Zod v4 schemas and one route manifest generate runtime validation, OpenAPI 3.1, Scalar/agent documentation, a TypeScript client and an explicitly allowlisted MCP tool manifest. The Vite console consumes the generated REST client. tRPC is removed.

Run MCP as a separate role that forwards a caller's short-lived OAuth token through the REST API. It has no repositories or domain-service entry point. New REST operations are not MCP tools unless their route metadata explicitly enables and classifies them. Security-sensitive/destructive operations are excluded at launch.

Organization deletion is owner self-service through the REST API. Requesting deletion immediately suspends new inference/admin mutation, then a durable Node worker drains reservations, reconciles and refunds refundable unused credit, destroys trace keys/objects, revokes access and pseudonymizes legally required financial evidence. One `organization_deletions` workflow row records recoverable state; no generic workflow engine is added.

## Why

A public, documented resource API is easier for customers, agents and integrations to adopt than a UI-private RPC protocol. Generating all derivative artifacts from one runtime-validated contract prevents schema/client/docs drift. MCP must reuse normal authorization rather than become a privileged second API.

Deletion crosses financial, cache, object-storage and identity boundaries, so a retryable workflow is required for correctness. Operator-only closure would fail the customer product contract.

## Consequences

- positive: one structured API for UI, automation and agents;
- positive: every public field/operation is description-gated and OpenAPI drift/breaking changes fail CI;
- positive: MCP exposure is auditable and cannot bypass REST authorization;
- positive: organization owners can leave without support while money and legal evidence remain correct;
- negative: the team maintains OpenAPI/client/MCP generators and an OAuth surface;
- negative: deletion/refund/purge fault testing is a launch requirement;
- limit: the inference API remains protocol-native under `/v1` and is not generated from control Zod schemas;
- limit: stateful MCP sessions and sensitive/destructive tools are deferred.

## Detailed contracts

- [REST, OpenAPI and MCP](../../product/docs/REST_OPENAPI_MCP_IMPLEMENTATION.md)
- [Organization deletion](../../product/docs/ORGANIZATION_DELETION.md)
