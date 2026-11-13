# MCP

The Gradiated MCP server at `https://mcp.gradiated.com/mcp`. It turns
operations from the API's OpenAPI document into MCP tools and calls the API
with the caller's credential, so each tool has exactly the authority of the
equivalent API request. `https://mcp.gradiated.com/` serves a page generated
from the same tool definitions and from `src/clients.ts`, with setup steps for
each client.

## Tools

`src/tools/config.ts` has one entry per API operation, typed against the
generated `OperationId` so a new route fails to compile until it has one. An
entry either disables the operation with a reason, or names its tool. It may add
guidance that names other tools, rename arguments, hide them (optionally with a
fixed value), require a field the API accepts in place of another, offer only
the configured arguments, pin the response schema, and send the call to the
gateway instead of the API. A tool's arguments are the operation's path and
query parameters and its JSON body fields, flattened into one object.
`workspace_id` comes from the credential and is never an argument.

Argument descriptions come from the API's Zod contracts, through the OpenAPI
document; building fails when an offered argument has none. Each tool's output
schema is its success response schema, and results carry the parsed JSON as
`structuredContent` as well as text. Tasks, versions and files are named by
their names: the API accepts a name wherever it takes a version or file ID.

Building also fails, and so do the tests, when an entry names a missing
operation or argument, hides a required argument without a value, or two
arguments or tools share a name. After adding an API route, run
`pnpm --filter @gradiated/api openapi:generate` and add its entry.

`src/prompts.ts` has the MCP prompts: task version reviews and comparisons,
failed generations and usage.

## Authentication

Clients either sign in with OAuth or send a workspace API key. Both go in
`Authorization: Bearer`; a key may also use `x-api-key`. The server identifies
the credential's workspace with `GET /api/v1/credentials/current`, then
forwards the credential on each call. The API lets either act as its member,
the key's creator or the user who consented, under
`/api/v1/workspaces/{its workspace}`, except credential management and changes
to the workspace itself. The server forwards the client's address so the API's
per-IP limits apply per client.

The API is the OAuth authorization server, Better Auth's OAuth provider at
issuer `https://api.gradiated.com/api/auth`, with its RFC 8414 metadata at
`https://api.gradiated.com/.well-known/oauth-authorization-server/api/auth`.
A request without a credential gets a 401 whose `WWW-Authenticate` names this
server's RFC 9728 metadata, `/.well-known/oauth-protected-resource/mcp`, which
points at that issuer. Clients register themselves (dynamic client
registration, public clients with PKCE), and the user signs in and consents in
the console at `/oauth/consent`, choosing one workspace. The consent's
reference ID is that workspace; access tokens are opaque, prefixed `grado_`,
last an hour, and carry the `mcp` scope and the workspace. Refresh tokens last
30 days.

The server caches each credential's identity in Valkey for five minutes, so
most requests skip `GET /api/v1/credentials/current`; revocation still applies
to every tool call, which the API authorizes. Entries are named and encrypted
(AES-256-GCM) with keys derived from the credential, so the cache alone reveals
neither identities nor keys. Without Valkey, or when it is slow, requests check
the credential with the API.

`call_model` goes to the gateway, which takes only API keys. An API key is sent
as it is. An OAuth connection exchanges its token for a hidden one-hour key of
its member's (`POST /api/v1/credentials/current/inference-keys`), cached for at
most five minutes and renewed once when the gateway rejects it.

The transport is stateless Streamable HTTP with JSON responses. A result over
100,000 characters is refused with a request to narrow it.

## Operation

Prometheus metrics are served on `METRICS_PORT` (9464) at `/metrics`: HTTP
requests, tool calls by tool and outcome (`success`, `rejected` for caller
errors, `failed` for upstream ones), authentications, cache results, inference
keys and Valkey readiness. The `Gradiated / MCP` Grafana dashboard and the
`gradiated.mcp` alerts read them.

## Local

`pnpm dev` from `product/` runs it on `http://127.0.0.1:3007` against the local
API. Open `/` for the generated page.
