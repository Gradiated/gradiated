# MCP

The Gradiated MCP server at `https://mcp.gradiated.com/mcp`. It turns
operations from the API's OpenAPI document into MCP tools and calls the API
with the caller's credential, so each tool has exactly the authority of the
equivalent API request. `https://mcp.gradiated.com/` serves a page generated
from the same tool definitions and from `src/clients.ts`, with setup steps for
each client.

## Tools

`src/tools/config.ts` has one entry per API operation. An entry either
disables the operation with a reason, or names its tool and may replace its
description and rename or describe arguments. A tool's arguments are the
operation's path and query parameters and its JSON body fields, flattened into
one object. `workspace_id` comes from the credential and is never an argument.
Building the tools fails, and so do the tests, when an API operation has no
entry, an entry names a missing operation or argument, or two arguments or
tools share a name. After adding an API route, run
`pnpm --filter @gradiated/api openapi:generate` and add its entry.

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

The transport is stateless Streamable HTTP with JSON responses. Results are cut
at 100,000 characters.

## Local

`pnpm dev` from `product/` runs it on `http://127.0.0.1:3007` against the local
API. Open `/` for the generated page.
