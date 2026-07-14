# Launch inference protocol contract

## Decision

Launch the Rust gateway with two generation surfaces:

1. OpenAI Responses Create compatibility at `POST /v1/responses`;
2. Anthropic Messages compatibility at `POST /v1/messages`.

Also expose `GET /v1/models`. Chat Completions, Embeddings, Images, Audio, Google GenerateContent, batches, files and provider-hosted tools are deferred until demand. This keeps the launch surface small while supporting the two modern agent/generation shapes customers are most likely to adopt.

“Compatible” means official OpenAI and Anthropic clients can call the documented Grad profile by changing base URL/key. It does not mean Grad implements every hosted product behind those providers' namespaces.

## Shared rules

- Authenticate a workspace key or native-channel credential before model resolution.
- Parse and bound the protocol-specific body before reserving money.
- Preserve exact direct provider/model identity and exact Grad release.
- Reject unsupported fields/capabilities before reserve; never ignore them.
- Return protocol-native JSON, SSE events and error envelopes.
- Publish a per-model capability matrix from the immutable release.
- Keep Product Intelligence retention separate from protocol state/storage flags.
- Use official SDK compatibility tests as release gates.

The internal request is a tagged union, not a flattened lowest-common-denominator object:

```rust
enum PublicProtocol { OpenAiResponses, AnthropicMessages }

enum CanonicalItem {
    Text { role: Role, text: String },
    Image { role: Role, source: ImageSource },
    ToolCall { id: String, name: String, arguments_json: String },
    ToolResult { call_id: String, content: Vec<CanonicalItem>, is_error: bool },
    Reasoning { encrypted_or_summary: ReasoningPayload },
}
```

Protocol adapters preserve ordering, identifiers and protocol-only fields required to reconstruct output. A capability that cannot be represented by the selected direct adapter or owned runtime is rejected rather than translated approximately.

## OpenAI Responses launch profile

Required launch behavior:

- `Authorization: Bearer <workspace-or-channel-key>` exactly as the OpenAI SDK sends it;
- text input as string or ordered input messages/items;
- `instructions`, model, output-token bound, temperature/top-p where the release supports them;
- function tools, tool choice, parallel tool-call flag and function-call outputs;
- text and strict JSON-schema output formats;
- reasoning effort and returned reasoning summary/encrypted item only when qualified;
- streaming event order and non-streaming accumulated response;
- authoritative input/cached-input/output/reasoning usage;
- request IDs, cancellation and protocol-native errors.

At launch Grad's Responses endpoint is stateless: omitted `store` behaves as `false`; explicit `store: false` is accepted. `store: true`, `previous_response_id`, Conversations, background mode, prompt templates, OpenAI-hosted tools, remote MCP tools, files and response retrieval/deletion are rejected with `unsupported_capability` before admission. Product Intelligence may still retain the trace under workspace policy; `store` controls a retrievable Responses resource, not Grad trace retention.

This profile avoids introducing a synchronous durable conversation store into the gateway, whose only internal request-path state dependency remains Valkey. Add stateful Responses only through a separate ADR with storage, deletion, latency and billing semantics.

Streaming follows named Responses SSE events and ends with exactly one terminal `response.completed`, `response.incomplete` or `response.failed`. Unknown future input fields/events are not silently accepted; adapters are fixture-versioned against the official schema.

## Anthropic Messages launch profile

Required launch behavior:

- `x-api-key: <workspace-or-channel-key>` and required `anthropic-version` exactly as the Anthropic SDK sends them;
- stateless multi-turn `user`/`assistant` messages and top-level system instructions;
- text content, tool definitions, `tool_use` and `tool_result` blocks;
- max tokens, stop sequences, temperature/top-p/top-k where supported;
- thinking/effort blocks only for releases that qualify them;
- streaming `message_start`, ordered content-block start/delta/stop, message delta and `message_stop` events;
- partial tool JSON deltas, terminal stop reason and authoritative usage;
- Anthropic-shaped status/error payloads, including overload behavior.

Image/document blocks, prompt-cache control fields, beta headers, server tools, containers and citations are capability-gated and off by default. A curated direct Anthropic release may enable a field only after passthrough and billing/retention tests prove exact behavior. Internal always-on KV cache does not imply support for Anthropic prompt-cache control or billing fields.

If both `Authorization` and `x-api-key` are present they must resolve to the same credential or the request fails before admission. Credentials are never forwarded upstream; the selected provider adapter injects its own provider secret.

`POST /v1/messages/count_tokens` is added with the first release whose exact tokenizer and protocol transform are qualified; it must not return an estimate labeled as exact.

## Models endpoint

`GET /v1/models` returns only models available to the authenticated workspace/channel and the two launch protocol capability profiles. Each entry identifies direct versus owned, context/output limits, text/tools/structured-output/reasoning support and stable model ID. Internal release digest, provider endpoint, cell/topology and canary weight remain hidden.

## Gateway module layout

```text
crates/gateway/src/protocol/
  openai_responses/{request,response,stream,error,fixtures}.rs
  anthropic_messages/{request,response,stream,error,fixtures}.rs
  models.rs
crates/gateway/src/canonical/{input,event,capability}.rs
crates/gateway/src/upstream/{openai,anthropic,owned}.rs
```

Each protocol owns parse/validate/encode. Each upstream adapter declares a machine-tested capability set and maps canonical items/events. Owned inference consumes the same bounded canonical serving contract and returns enough typed events for either public encoder.

## Verification

- OpenAI JavaScript/Python SDK `responses.create` streaming and non-streaming against fake and cheapest real provider/model.
- Anthropic JavaScript/Python SDK `messages.create` and streaming against fake and cheapest real provider/model.
- Golden fixtures for every accepted item, tool cycle, structured output, reasoning/usage and error.
- proptest-generated chunk boundaries/event interleavings prove streaming accumulation equals non-streaming output.
- generated unsupported-field/capability cases prove zero reservation and zero upstream call.
- cancellation, timeout, backpressure and provider faults prove one settlement and valid terminal wire behavior.
- direct passthrough differential tests compare normalized official-provider behavior without asserting provider-unstable text.
- owned-runtime conformance runs both public protocols against the same exact release.

Protected CI uses synthetic tiny prompts, hard token/spend/time limits and secret-presence skips. It stores only sanitized protocol/usage evidence.

## Primary references

- [OpenAI Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Anthropic Messages create reference](https://platform.claude.com/docs/en/api/messages/create)
- [Anthropic streaming event contract](https://platform.claude.com/docs/en/build-with-claude/streaming)
