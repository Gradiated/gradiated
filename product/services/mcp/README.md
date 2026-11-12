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

Clients send a workspace API key as `Authorization: Bearer` or `x-api-key`.
The server identifies its workspace with `GET /api/v1/api-keys/current`, then
forwards the key on each call. The API lets a key act as the member who created
it under `/api/v1/workspaces/{its workspace}`, except credential management and
changes to the workspace itself. The server forwards the client's address so
the API's per-IP limits apply per client.

The transport is stateless Streamable HTTP with JSON responses. Results are cut
at 100,000 characters.

## Local

`pnpm dev` from `product/` runs it on `http://127.0.0.1:3007` against the local
API. Open `/` for the generated page.
