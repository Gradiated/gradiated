# Mcp

The customer MCP server: tools generated from the API's OpenAPI document that call the API, or the gateway for model calls, with the caller's workspace API key or OAuth access token.

## entrances

- index: anyone reads the generated setup page and tool list
  handler: renderIndexPage in src/index-page.ts
  trust: anonymous
  control: none — the page lists public setup steps and tool descriptions only
- resource metadata: an MCP client discovers the authorization server from the RFC 9728 document
  handler: createApp in src/app.ts
  trust: anonymous
  control: none — the document names the public resource and issuer only
- tools: a client lists or calls tools over Streamable HTTP
  handler: createApp in src/app.ts
  trust: workspace-credential

## invariants

- caller authority: Every tool call is the equivalent API request made with the caller's own credential, in the credential's workspace.
  over: every tools/call: workspace_id from the model, unknown and missing arguments, and keys or tokens the API rejects
  via: the MCP endpoint
  because: the service holds no credentials of its own, so the API's authorization is the only check and must see the caller
  crossing: workspace-credential -> control-plane
  kinds: credential, identity
  checklist: capability-authorization dismissed: the API authorizes each request; key confinement holds the check
  checklist: destination-confinement declared as caller authority; requests go only to the configured API and inference origins
  checklist: input-validation dismissed: the API and gateway validate every argument they receive
- sealed cache: A cached identity or inference key is readable only with the credential it was cached for.
  over: every credential cache entry
  via: createCredentialCache in src/cache.ts
  because: Valkey is shared with other services, and an inference key read from it would let anyone call models as the member
  crossing: workspace-credential -> control-plane
  kinds: credential
  checklist: encrypted-storage declared as sealed cache; entries are AES-256-GCM encrypted under a key derived from the credential and named by a separate derivation
- inference key confinement: An OAuth connection's inference key is used only for its own model calls and lives in the cache at most five minutes.
  over: call_model with an OAuth access token
  via: createCredentials in src/credentials.ts
  because: the key outlives a revoked token for as long as it is cached
  crossing: workspace-credential -> control-plane
  kinds: credential
