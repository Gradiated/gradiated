# REST, OpenAPI and MCP implementation blueprint

## Decision

The control plane is a versioned REST API implemented with Hono. tRPC is removed. The Vite console, automation, CLI and generated MCP server all consume the same HTTP contract.

The authoring chain is:

```text
described Zod v4 schemas + Hono route manifest
  -> runtime request/response validation
  -> OpenAPI 3.1 artifact
  -> Scalar reference + agent Markdown
  -> generated TypeScript client
  -> allowlisted MCP tools
```

OpenAPI is generated output, not a second handwritten source. The MCP role is an authenticated REST client, not an alternate domain-service entry point.

## Dependencies

Pin and renovate these as one compatibility set:

- `hono` and `@hono/zod-openapi` for routing, validation and OpenAPI 3.1 generation;
- Zod v4 for boundary schemas and metadata;
- `@scalar/hono-api-reference` for the human API reference;
- `@scalar/openapi-to-markdown` for `/api/llms.txt`;
- `openapi-typescript` and `openapi-fetch` for the generated console/CLI client;
- `@modelcontextprotocol/sdk` for the remote Streamable HTTP MCP role.

Do not add tsoa, Nest, Express, a second validator, a second API description DSL or a generic OpenAPI-to-MCP runtime dependency. The Grad generator is small, build-time code because it must enforce Grad authorization and exposure rules.

## Source layout

```text
product/
  apps/
    control/src/
      app.ts
      roles/{api,financial,intelligence,trace-access,mcp}.ts
      http/
        context.ts
        errors.ts
        idempotency.ts
        pagination.ts
        route-manifest.ts
        routes/{session,organizations,members,workspaces,keys,billing,models,usage,traces,recommendations}.ts
      mcp/{generator,server,rest-client}.ts
    web/src/api/
  packages/
    api-contracts/src/{common,organizations,workspaces,keys,billing,usage,traces,models}.ts
    control-client/src/{generated,client}.ts
  openapi/control-v1.json
  scripts/{generate-openapi,check-openapi-descriptions,generate-control-client,generate-mcp-manifest}.ts
```

Domain services and repositories remain under `packages/domain` and `packages/db`. They do not import Hono, OpenAPI, MCP or browser packages.

## Route definition contract

Every route is declared once with a wrapper around `createRoute`:

```ts
type AgentExposure =
  | { enabled: false; reason: string }
  | {
      enabled: true;
      toolName: string;
      purpose: string;
      readOnly: boolean;
      destructive: boolean;
      idempotent: boolean;
      openWorld: boolean;
    };

type GradOperation = {
  method: HttpMethod;
  path: `/api/v1/${string}`;
  operationId: string;
  tags: readonly string[];
  summary: string;
  description: string;
  auth: 'session' | 'session_or_oauth' | 'webhook' | 'internal';
  idempotency: 'forbidden' | 'optional' | 'required';
  agent: AgentExposure;
  request: RequestSchemas;
  responses: ResponseSchemas;
};
```

The wrapper rejects duplicate method/path or `operationId`, missing success/error schemas, unspecified authentication, undocumented side effects and unclassified MCP exposure. Handlers receive only validated path/query/header/body values plus server-derived actor context.

Each operation description states purpose, authorization, important preconditions, side effects, retry/idempotency behavior and sensitive output. Each exposed field has a Zod `.meta({ description, examples })` after its final refinement. Metadata lost by a later Zod transformation is a build failure.

## Description and schema gate

`generate-openapi` imports every route and calls `getOpenAPI31Document`. `check-openapi-descriptions` recursively resolves local `$ref`s and fails when any of these is missing:

- operation summary, description, stable `operationId`, tags and security;
- path/query/header parameter description;
- request and response media type/schema;
- every object property description, including nested union variants;
- every enum's field-level meaning where its name is not self-explanatory;
- success and declared error response descriptions;
- at least one safe example for IDs, money, cursors, states and non-obvious inputs.

Undescribed `additionalProperties` is forbidden. An intentional dictionary must have a bounded value schema and describe key syntax. Secret examples are synthetic. OpenAPI lint, generated-client compile and a clean Git diff are required in CI.

This output check is stronger than an AST convention: it proves the artifact seen by humans, generators and agents contains the descriptions.

## HTTP conventions

- Customer management endpoints live under `/api/v1`; `/v1` remains reserved for inference protocols.
- JSON uses `snake_case` to match public inference and cross-language clients.
- IDs are opaque strings; UTC timestamps are RFC 3339 strings; integer money micros are decimal strings on the wire.
- Lists return `{ data, next_cursor }` with opaque bounded cursors and deterministic ordering.
- Mutations that can create duplicate external or financial effects require `Idempotency-Key` and persist the result by actor, operation and key.
- Creation returns `201`; asynchronous workflows return `202` with a resource/status URL; deletion returns `204` only after synchronous completion.
- Cookie-authenticated unsafe requests enforce Origin, Fetch Metadata and CSRF. OAuth bearer requests do not use cookies.
- Responses include `X-Request-Id`; sensitive responses use `Cache-Control: no-store`.

Errors use `application/problem+json`:

```text
type, title, status, detail, instance
code, request_id
field_errors[] { path, code, message }   # validation only
retry_after_seconds?                     # bounded transient failures only
```

`code` is a closed stable enum. Stack traces, SQL errors, provider payloads and authorization existence leaks never cross the boundary.

## Initial resource surface

| Resource | Initial operations | MCP launch exposure |
| --- | --- | --- |
| session | current actor and organizations | read |
| organizations | list/create/get/update; request/get/cancel deletion | read/create/update; deletion excluded |
| organization members/invitations | list/invite/reissue/revoke/update/remove/accept | list/invite; revoke/removal excluded initially |
| workspaces | list/create/get/update/archive non-Default | read/create/update |
| workspace members | list/add/update/remove | read; writes added only after confirmation UX exists |
| API keys | list/create/revoke | list only; one-time secrets are excluded |
| billing | balance, top-up checkout, transactions | read only; checkout excluded |
| models | list/get | read |
| usage/traces | bounded list/aggregate, 31-day bounded streaming usage CSV, trace detail/delete | list/aggregate; CSV, payload detail and deletion excluded |
| recommendations/evaluations | list/get/accept/dismiss/start bounded evaluation | read plus explicitly safe evaluation start later |

Stripe webhooks, internal release/fleet commands, trace-decrypt grants and research mutations are documented in private specs and never emitted as customer MCP tools.

## Authentication and authorization

The browser uses Better Auth email/password, verification/recovery and secure session cookies. Social login is deferred. Remote MCP uses OAuth authorization-code + PKCE and short-lived bearer tokens backed by Better Auth's authorization tables. Every bearer token is user-bound and organization-scoped; selecting a workspace still requires current membership. Machine-to-machine management credentials are deferred until a real automation customer exists.

Authorization is executed in REST middleware/domain services on every request. The OpenAPI security declaration and MCP annotations are documentation hints, not enforcement. MCP cannot supply organization IDs to widen its grant.

## Generated clients and docs

CI commits `product/openapi/control-v1.json` and generated TypeScript types. `openapi-fetch` is the only generated client runtime; the Vite app uses TanStack Query wrappers around it. UI features may not call Hono handlers or repositories directly.

Published endpoints are:

```text
GET /api/openapi.json     canonical control OpenAPI 3.1 artifact
GET /api/docs             pinned Scalar reference
GET /api/llms.txt         generated agent-readable Markdown
POST|GET|DELETE /mcp      authenticated MCP Streamable HTTP transport
```

The deployed OpenAPI digest is exposed in a response header and build metadata. Docs default to production server examples but clearly show sandbox/local URLs.

## MCP generation

`generate-mcp-manifest` reads the committed OpenAPI plus `x-grad-agent` operation extensions emitted by the route wrapper. For each `enabled: true` operation it generates:

- stable tool name from explicit `toolName`, never heuristics;
- tool title/description from operation metadata;
- input JSON Schema from path/query/body fields with organization context removed;
- structured output schema from the selected success response;
- `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint`;
- a binding to one generated REST-client operation.

The MCP role validates tool input, forwards the caller's OAuth bearer token and idempotency key to the REST API, validates the response, and returns structured content. It has no database, Stripe, KMS or domain-service imports. A tool cannot exist unless its REST operation exists and is allowlisted; a newly added REST operation defaults to `enabled: false` with a required reason.

Organization deletion, one-time key secrets, trace plaintext, checkout creation and operator actions remain REST/web-only at launch. Tool annotations improve host UX but never replace server authorization, recent reauthentication or deterministic confirmation.

Use stateless Streamable HTTP initially. Stateful sessions, prompts, resources, sampling and elicitation are deferred until a product workflow needs them.

## Evolution rules

- Additive optional response fields are allowed within `v1`; removing/renaming fields or changing meaning requires `v2` or an explicit deprecation window.
- Request fields default to rejected unknown keys for mutations and compatibility-reviewed behavior for filters.
- OpenAPI diffs classify additive, breaking and documentation-only changes; breaking changes fail main.
- Generated clients pin the artifact digest. MCP tool names do not change when URL layout changes inside a version.
- Internal Protobuf remains for hot cross-language streaming contracts only; it does not generate the management API.

## Verification

Required tests:

- Vitest examples for every operation's success, validation, auth and problem response;
- fast-check sequences for idempotent create/mutation retry, cursor stability, tenant lineage and authorization changes;
- OpenAPI snapshot plus semantic breaking-change and description traversal checks;
- generated TypeScript client compile and Vite integration tests against the Hono app;
- MCP manifest snapshot proving exact allowlist, descriptions, schemas and annotations;
- MCP invocation tests proving REST middleware is traversed and unmarked/destructive routes are unreachable;
- OAuth expiry/revocation/scope tests and cross-organization denial;
- Playwright accessibility/quickstart tests using only the generated client.

## Build packages

1. `API-00`: route wrapper, problem details, pagination/idempotency and description checker.
2. `API-01`: migrate session/organization/workspace/key routes from tRPC; remove tRPC dependencies and server/client code.
3. `API-02`: generate/commit OpenAPI 3.1, publish Scalar and agent Markdown, add breaking/drift CI.
4. `API-03`: generate `openapi-typescript` client and migrate Vite/TanStack Query calls.
5. `API-04`: billing, models, usage/trace and recommendation resources.
6. `API-05`: OAuth-protected stateless MCP role and allowlisted generated tools.

## Primary references

- [Hono Zod OpenAPI example](https://hono.dev/examples/zod-openapi)
- [Hono Scalar integration](https://hono.dev/examples/scalar)
- [Zod metadata and registries](https://zod.dev/metadata)
- [Better Auth OAuth 2.1 Provider and MCP resource-server support](https://better-auth.com/docs/plugins/oauth-provider)
- [MCP TypeScript server SDK](https://ts.sdk.modelcontextprotocol.io/server)
- [MCP tool annotations](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
