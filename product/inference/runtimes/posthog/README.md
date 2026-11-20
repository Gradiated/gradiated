# PostHog decision runtimes

Shared serving code and the parity check for the two PostHog SystemOne models, each served by its own bundle on SGLang:

- [`posthog/jevk5`](../jevk5/README.md): JevK5, Qwen3.5-4B, answer-letter readout.
- [`posthog/jeeves`](../jeeves/README.md): Jeeves, Qwen3.5-9B with a pointer head.

`posthog_common.py` is linden-1's structure: Kev's bounded ASGI adapter (`kev_http`, from
`runtimes/kev/adapter.py`) validates each request against the gateway contract
(`product/packages/contracts/src/systemone.ts`), and a loopback SGLang 0.5.21 engine returns the log probabilities of
chosen token ids for one generated token per prompt. Prompts are sent as token ids, so SGLang never tokenizes. An
answer that would fail the gateway's checks (`product/services/gateway/src/runtime/systemone.rs`) is never returned.
Single-outcome questions (one option or one level), which the gateway accepts and PostHog refuses, are answered with
certainty without the model. Up to 8 requests run at once; a ninth gets 429.

## Contract against PostHog's

PostHog serves both models from `PostHog/hogference` (`jev/`, `jeeves/`) at `POST /v1/systemone`. Their callers reach
ours through the gateway, which enforces our contract before a runtime sees the request.

|                   | PostHog (hogference)                                                        | Gradiated gateway and these runtimes                                                             | PostHog callers                                               |
| ----------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| `model`           | optional; echoed back, else `JevK5` / `Jeeves`                              | required, exactly `posthog/jevk5` or `posthog/jeeves`; echoed                                    | break without it                                              |
| Unknown fields    | top level ignored; jev ignores unknown question fields, jeeves rejects them | rejected (only `session_id` and `service_tier: "default"` besides `model`, `state`, `questions`) | break if they send extras                                     |
| `state`           | any JSON                                                                    | string, object or array                                                                          | break on scalar or null states                                |
| `instructions`    | required (400 without)                                                      | optional; asked with none                                                                        | no                                                            |
| `choice` criteria | object, or a list of names meaning `{name: null}`                           | object only                                                                                      | **break on list criteria** (2 of jev's 46 fixtures use lists) |
| Options           | at least 2; jev unlimited (knockout), jeeves 255                            | 1 to 255; one option answers 1.0 without the model                                               | break above 255 options (jev only)                            |
| `noul` criteria   | optional; jev ignores other keys, jeeves rejects them                       | optional object with only `true` / `false`, or null                                              | break on other keys (jev only)                                |
| Questions         | unlimited                                                                   | 1 to 64, names of 1 to 200 characters                                                            | break above 64                                                |
| JSON bounds       | none                                                                        | no duplicate keys or non-finite numbers, depth 32, runtime body 1 MiB                            | rarely                                                        |
| Prompt size       | 16,384 tokens a prompt; 413 past 3 times the queue limit                    | 16,384 tokens a prompt and 65,536 a request (every pass counted), else 422                       | status codes differ                                           |
| Errors            | 400, 413, 429 (queue), 499, 500                                             | 422, 413 (body), 429 (8 in flight), 500                                                          | status codes differ                                           |
| `noul` answer     | `type`, `noul`, `confidence`                                                | `type`, `noul` (the gateway rejects `confidence`; it is max(p, 1 - p))                           | break if they read it                                         |
| `choice` answer   | `type`, `choice`, `confidence` (top probability), `probabilities`           | the same, unrounded                                                                              | no                                                            |
| `score` answer    | `type`, `score` (expected level), `confidence`, `probabilities`             | the same plus `legend` (level index to text), which the gateway requires                         | additive                                                      |
| `usage`           | `input_tokens` (every pass's whole prompt), `output_tokens: 0`              | the same plus `cached_input_tokens: 0`                                                           | additive                                                      |
| `latency_ms`      | runtime time                                                                | runtime time                                                                                     | no                                                            |

Accepting PostHog's requests unchanged would need gateway changes (list criteria, optional `model`, more questions
and options, `noul` confidence); this runtime keeps exactly what the gateway accepts today.

## Parity

`parity.py` replays PostHog's 46 reference cases (`../jevk5/reference.json`, `../jeeves/reference.json`, copied from
`PostHog/hogference` at 55eaed1a) against a deployed runtime, one question a request, and applies hogference's gates:
|Δp| ≤ 0.08 for JevK5 and ≤ 0.15 for Jeeves, with no top-answer change on a clear decision. It needs a GPU runtime;
run it once the L4 hosts are enrolled and a pool is staged:

```sh
GRADIATED_API_KEY=... python3 product/inference/runtimes/posthog/parity.py --model posthog/jeeves \
  --url https://api.gradiated.com --deployment-id "$POD_UID"
```

It also prints any case whose `input_tokens` differ from the reference. Measured offline with each checkpoint's
tokenizer and `transformers` 5.12.1: every Jeeves prompt has the reference's token count and the same token ids as
Jeeves's own code; every JevK5 case of up to 16 options has the reference's count (the knockout's final pass depends on
the answers, so its count is checked on a GPU).
