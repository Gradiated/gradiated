# Gateway multi-protocol inference surface

- Date: 2026-08-27
- Status: accepted
- Decision: serve Anthropic Messages and OpenAI Responses alongside Chat
  Completions from one host and one Rust gateway, translating at the HTTP edge
  through `switchyard-translation`, keeping the OpenAI Chat Completions
  pipeline as the single internal request format.

## Question

How do we support Claude Code (`/v1/messages`), Codex (`/v1/responses`), and
existing OpenAI clients (`/v1/chat/completions`) without complicating the
gateway hot path or the model runtime contract?

## Decision

1. One public URL, path decides protocol. `api.gradiated.com` serves
   `/v1/chat/completions`, `/v1/messages`, `/v1/messages/count_tokens`,
   `/v1/responses`, and `/v1/models` from the same gateway. The Anthropic SDK
   base URL is the bare host; OpenAI SDK and Codex base URLs are the host with
   or without `/v1`; both spellings are aliases of the same handlers.
2. Backwards compatibility is preserved: the `/openai/v1/*` ALB prefix-strip
   route is unchanged, and a second multi-match HTTPRoute rule serves `/v1` and
   the bare inference paths directly.
3. The internal pipeline stays OpenAI Chat Completions native. Inbound
   Messages and Responses bodies decode to a neutral IR and encode to Chat
   Completions JSON before `ChatCompletionRequest::parse`; responses and
   streams re-encode from the normalized Chat Completions output to the
   caller's format. Admission, routing, tokenization, usage normalization,
   settlement, and finalization are untouched.
4. Translation uses the pinned `switchyard-translation = "=0.2.0"` crate
   (Apache-2.0, NVIDIA NeMo), wrapped behind `src/protocol.rs`. If the crate
   stalls or misbehaves, the module boundary makes a hand-rolled replacement a
   local change.
5. Streaming is wire-neutral inside the gateway: the generation task emits
   typed `StreamItem`s (chunk, error, done) and only the HTTP edge frames SSE
   per protocol, including Anthropic `event:` names.
6. Errors render per protocol: OpenAI envelopes for Chat and Responses, the
   `{"type":"error","error":{...}}` envelope with `event: error` for Messages.
7. `POST /v1/messages/count_tokens` counts the translated request locally with
   the exact served tokenizer. It approximates Anthropic's own tokenizer and is
   documented as such.
8. The Responses surface is stateless. `store`, `previous_response_id`, and
   `conversation` requests are rejected with 400. Codex clients work stateless
   by resending context.

## Field policy

- Gateway-owned fields map strictly (`model`, `max_tokens`/`max_tokens`
  equivalence, `stop`/`stop_sequences`, tools, tool results, stream).
- Model-specific parameters flow through the existing per-model
  `supported_parameters` gate; unadvertised parameters are rejected, not
  dropped.
- Cosmetic fields with no chat equivalent (for example `cache_control`,
  `metadata`, `anthropic-version`) are dropped with diagnostics; the gateway
  does not implement prompt caching through request fields.

## Alternatives considered

- Forward to the model runtime (SGLang, vLLM): neither runtime serves the
  Anthropic protocol; Responses support is partial and pinned to runtime
  images. It would couple the customer API surface to GPU redeployments and
  duplicate translation in every runtime. Rejected.
- A separate translation service in front of the gateway: adds a hop on the
  hot path, a second deployment, and a second auth boundary for code the
  gateway already runs locally. Rejected.
- Hand-rolled codecs now: roughly two to four thousand lines of streaming
  state machines with no upstream coverage. Switchyard provides tested
  codecs and diagnostics; the seam preserves the option to replace it.

## Verification

- Unit tests cover request translation, response translation, full stream
  event sequences, and per-protocol error frames for all three formats.
- HTTP-level tests cover route aliases, protocol error envelopes, SSE event
  framing, `x-api-key` authentication, and stateful-Responses rejection.
- End-to-end conformance with real Claude Code and Codex clients against the
  pinned production SGLang deployment follows the existing release
  conformance process.

## Consequences

- Codex onboarding is unblocked through a separate wizard-managed profile.
  Claude Code uses manual environment configuration so the wizard does not
  change its default route.
- New provider formats become an additive `Protocol` variant plus fixtures.
- The gateway now depends on a young third-party crate; pinning, the module
  boundary, and conformance fixtures bound that risk.
