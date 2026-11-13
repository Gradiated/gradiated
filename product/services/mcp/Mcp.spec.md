# Mcp

The customer MCP server: tools generated from the API's OpenAPI document that call the API with the caller's workspace API key.

## entrances

- index: anyone reads the generated setup page and tool list
  handler: renderIndexPage in src/index-page.ts
  trust: anonymous
  control: none — the page lists public setup steps and tool descriptions only
- tools: a client lists or calls tools over Streamable HTTP
  handler: createApp in src/app.ts
  trust: customer-api-key

## invariants

- caller authority: Every tool call is the equivalent API request made with the caller's own key, in the key's workspace.
  over: every tools/call: workspace_id from the model, unknown and missing arguments, and keys the API rejects
  via: the MCP endpoint
  because: the service holds no credentials of its own, so the API's authorization is the only check and must see the caller
  crossing: customer-api-key -> control-plane
  kinds: credential, identity
  checklist: capability-authorization dismissed: the API authorizes each request; key confinement holds the check
  checklist: destination-confinement declared as caller authority; requests go only to the configured API origin
  checklist: input-validation dismissed: the API validates every argument it receives
