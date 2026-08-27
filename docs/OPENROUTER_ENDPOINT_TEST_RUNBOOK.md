# OpenRouter endpoint test runbook

- status: preflight runbook
- date: 2026-08-26
- owner: Gradiated Ltd
- endpoint: `https://api.gradiated.com/openai/v1`
- target model: DeepSeek V4 Flash 0731

Use this runbook after the DeepSeek endpoint is available. It tests the public
provider path that OpenRouter will call. Do not run only against the private
model runtime.

OpenRouter does not publish its exact baseline prompts or thresholds. It states
that initial test traffic validates API compatibility, latency, throughput, and
error handling. It also tests only the capabilities declared in `/models`.
These checks reproduce that public contract and add Gradiated release gates.

Primary references:

- [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers)
- [OpenRouter provider application](https://openrouter.ai/providers/apply)
- [OpenRouter provider schema](https://openrouter.ai/docs/assets/provider-monitor-schema-v2.openapi.json)

## Pass conditions

The endpoint is ready for OpenRouter baseline testing when:

- all required checks in this runbook pass;
- only tested capabilities appear in `/models`;
- streaming and non-streaming usage totals are correct;
- overload returns an early `429` response;
- a representative load test records acceptable TTFT and throughput;
- a 24-hour soak completes without an unplanned error;
- restart and drain tests complete without routing traffic to an unready model.

OpenRouter gives normal routing priority at 95% or higher uptime. Use a higher
internal release target. Do not treat 95% as the Gradiated availability SLO.

## Test setup

Run the commands from the repository root. Install `curl` and `jq` first.

Set the non-secret values:

```sh
export GRADIATED_BASE_URL='https://api.gradiated.com/openai/v1'
export GRADIATED_MODEL='deepseek/deepseek-v4-flash-0731'
export GRADIATED_TEST_RUN=".agents/runtime/openrouter-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$GRADIATED_TEST_RUN"
```

Load the dedicated OpenRouter provider key into
`GRADIATED_OPENROUTER_KEY` from the approved secret store. Do not put the key
in this file, a command argument, shell history, or a committed result.

Confirm that the variables exist without printing the key:

```sh
: "${GRADIATED_BASE_URL:?set GRADIATED_BASE_URL}"
: "${GRADIATED_MODEL:?set GRADIATED_MODEL}"
: "${GRADIATED_OPENROUTER_KEY:?load the provider key from the secret store}"
: "${GRADIATED_TEST_RUN:?set GRADIATED_TEST_RUN}"
```

Store only non-sensitive test output under `.agents/runtime/`. Do not store
private prompts, customer data, authorization headers, or credentials.

## 1. Catalog and TLS

Fetch the catalog through the public TLS endpoint:

```sh
curl --fail-with-body --silent --show-error \
  --connect-timeout 10 --max-time 30 \
  "$GRADIATED_BASE_URL/models" \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -o "$GRADIATED_TEST_RUN/models.json"
```

Validate the required model document:

```sh
jq -e --arg model "$GRADIATED_MODEL" '
  (.data | type == "array" and length > 0) and
  any(.data[];
    .id == $model and
    .schema_version == "2.4" and
    (.id == (.id | ascii_downcase)) and
    (.created | type == "number") and
    (.is_ready != false) and
    any(.input_modalities[]?; .type == "text") and
    any(.output_modalities[]?; .type == "text" and .streaming == true) and
    (.datacenters | type == "array" and length > 0)
  )
' "$GRADIATED_TEST_RUN/models.json"
```

Inspect the exact advertised contract:

```sh
jq --arg model "$GRADIATED_MODEL" '
  .data[] | select(.id == $model) |
  {
    id,
    name,
    schema_version,
    hugging_face_id,
    quantization,
    input_modalities,
    output_modalities,
    capacity,
    datacenters,
    deployment_region,
    compliance,
    is_ready
  }
' "$GRADIATED_TEST_RUN/models.json"
```

Confirm manually that:

- prices are strings in USD base units;
- context and output limits match the deployed runtime;
- capacity does not exceed measured capacity;
- the quantization matches the deployed checkpoint;
- the region and data policy are correct;
- no private runtime URL, secret, artifact path, or internal release digest is
  present;
- unsupported parameters and features are absent.

## 2. Authentication

A missing key must return `401`:

```sh
status="$(curl --silent --show-error \
  --output "$GRADIATED_TEST_RUN/missing-key.json" \
  --write-out '%{http_code}' \
  "$GRADIATED_BASE_URL/models")"
test "$status" = '401'
```

An invalid key must return `401`:

```sh
status="$(curl --silent --show-error \
  --output "$GRADIATED_TEST_RUN/invalid-key.json" \
  --write-out '%{http_code}' \
  "$GRADIATED_BASE_URL/models" \
  -H 'Authorization: Bearer invalid-openrouter-preflight-key')"
test "$status" = '401'
```

Confirm that both error bodies use the stable public error shape. Confirm that
neither body contains stack traces or internal service details.

## 3. Non-streaming completion

Send a deterministic, non-sensitive request:

```sh
jq -n --arg model "$GRADIATED_MODEL" '{
  model: $model,
  messages: [{role: "user", content: "Reply with exactly: ready"}],
  max_tokens: 16,
  temperature: 0,
  stream: false
}' | curl --fail-with-body --silent --show-error \
  --max-time 180 \
  "$GRADIATED_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  -o "$GRADIATED_TEST_RUN/non-stream.json"
```

Validate the response and usage totals:

```sh
jq -e --arg model "$GRADIATED_MODEL" '
  .object == "chat.completion" and
  .model == $model and
  (.choices | type == "array" and length > 0) and
  (.choices[0].message.content | type == "string" and length > 0) and
  (.choices[0].finish_reason | type == "string") and
  (.usage.prompt_tokens | type == "number" and . > 0) and
  (.usage.completion_tokens | type == "number" and . > 0) and
  (.usage.total_tokens == (.usage.prompt_tokens + .usage.completion_tokens))
' "$GRADIATED_TEST_RUN/non-stream.json"
```

## 4. Streaming completion

Send the same request with streaming enabled:

```sh
jq -n --arg model "$GRADIATED_MODEL" '{
  model: $model,
  messages: [{role: "user", content: "Reply with exactly: ready"}],
  max_tokens: 16,
  temperature: 0,
  stream: true,
  stream_options: {include_usage: true}
}' | curl --fail-with-body --silent --show-error --no-buffer \
  --max-time 180 \
  "$GRADIATED_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  -o "$GRADIATED_TEST_RUN/stream.sse"

tr -d '\r' \
  < "$GRADIATED_TEST_RUN/stream.sse" \
  > "$GRADIATED_TEST_RUN/stream-normalized.sse"
```

Confirm that the stream terminates with `[DONE]`:

```sh
grep -qx 'data: \[DONE\]' "$GRADIATED_TEST_RUN/stream-normalized.sse"
```

Extract and validate all JSON events:

```sh
sed -n 's/^data: //p' "$GRADIATED_TEST_RUN/stream-normalized.sse" |
  grep -v '^\[DONE\]$' |
  jq -s -e '
    length > 1 and
    (map(.choices[]?.delta.content? // empty) | join("") | length > 0) and
    (map(select(.usage != null)) | length == 1) and
    (map(select(.usage != null))[0].usage |
      .prompt_tokens > 0 and
      .completion_tokens > 0 and
      .total_tokens == (.prompt_tokens + .completion_tokens))
  ' > "$GRADIATED_TEST_RUN/stream-events.json"
```

Confirm manually that tokens arrive before completion. Confirm that the
terminal usage event is authoritative and that no earlier event reports a
different final total.

## 5. Stable error behavior

An unknown model must return `404`:

```sh
jq -n '{
  model: "gradiated/openrouter-preflight-model-does-not-exist",
  messages: [{role: "user", content: "test"}],
  max_tokens: 1
}' | curl --silent --show-error \
  --output "$GRADIATED_TEST_RUN/unknown-model.json" \
  --write-out '%{http_code}\n' \
  "$GRADIATED_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- |
  grep -qx '404'
```

An invalid parameter must return `400`:

```sh
jq -n --arg model "$GRADIATED_MODEL" '{
  model: $model,
  messages: [{role: "user", content: "test"}],
  max_tokens: 0
}' | curl --silent --show-error \
  --output "$GRADIATED_TEST_RUN/invalid-parameter.json" \
  --write-out '%{http_code}\n' \
  "$GRADIATED_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- |
  grep -qx '400'
```

Confirm that both error bodies:

- use the OpenAI-compatible error envelope;
- contain a stable error type and code;
- do not contain stack traces, credentials, or private service details;
- complete quickly and do not retry an invalid request upstream.

## 6. Multi-turn behavior

```sh
jq -n --arg model "$GRADIATED_MODEL" '{
  model: $model,
  messages: [
    {role: "user", content: "Remember the value 731. Reply with: stored"},
    {role: "assistant", content: "stored"},
    {role: "user", content: "What value did I ask you to remember? Reply with only the number."}
  ],
  max_tokens: 16,
  temperature: 0
}' | curl --fail-with-body --silent --show-error \
  --max-time 180 \
  "$GRADIATED_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  -o "$GRADIATED_TEST_RUN/multi-turn.json"

jq -e '
  (.choices[0].message.content | contains("731")) and
  (.usage.total_tokens > 0)
' "$GRADIATED_TEST_RUN/multi-turn.json"
```

## 7. Optional declared capabilities

Run a capability test only if the model document advertises that capability.
Remove the capability from `/models` if the test fails.

### Tool calling

Check whether tool calling is advertised:

```sh
jq -e --arg model "$GRADIATED_MODEL" '
  .data[] | select(.id == $model) |
  any(.output_modalities[]?;
    .type == "text" and
    (.supported_parameters.tools.type == "boolean"))
' "$GRADIATED_TEST_RUN/models.json"
```

If it is advertised, require one valid tool call:

```sh
jq -n --arg model "$GRADIATED_MODEL" '{
  model: $model,
  messages: [{role: "user", content: "Use get_weather for Warsaw."}],
  tools: [{
    type: "function",
    function: {
      name: "get_weather",
      description: "Get weather for a city",
      parameters: {
        type: "object",
        properties: {city: {type: "string"}},
        required: ["city"],
        additionalProperties: false
      }
    }
  }],
  tool_choice: {type: "function", function: {name: "get_weather"}},
  max_tokens: 128
}' | curl --fail-with-body --silent --show-error \
  --max-time 180 \
  "$GRADIATED_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  -o "$GRADIATED_TEST_RUN/tool-call.json"

jq -e '
  .choices[0].message.tool_calls[0].function.name == "get_weather" and
  (.choices[0].message.tool_calls[0].function.arguments | fromjson | .city == "Warsaw")
' "$GRADIATED_TEST_RUN/tool-call.json"
```

Also test streaming tool calls, multiple tools, parallel tool calls, and a tool
result continuation before declaring broad tool support.

### Structured output and reasoning

If structured output is advertised, test the exact JSON Schema request shape
and validate the returned JSON against that schema. If reasoning is advertised,
test each declared reasoning level and confirm its usage accounting. Do not
infer either capability from model marketing material.

## 8. Cancellation

Start a long streaming request and cancel it after two seconds:

```sh
set +e
jq -n --arg model "$GRADIATED_MODEL" '{
  model: $model,
  messages: [{role: "user", content: "Write a long technical report."}],
  max_tokens: 32768,
  stream: true
}' | curl --silent --show-error --no-buffer \
  --max-time 2 \
  "$GRADIATED_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  -o "$GRADIATED_TEST_RUN/cancelled-stream.sse"
cancel_status="$?"
set -e
test "$cancel_status" = '28'
```

Use runtime metrics to confirm that upstream generation stops promptly. The
client result alone does not prove upstream cancellation.

## 9. Capacity and performance

Run the approved external gateway load test at concurrency levels `1`, `4`,
`8`, `16`, and higher only when safe. Use unique prompts and a fixed output
length. Record:

- successful requests;
- `429` responses;
- unexpected `4xx` and `5xx` responses;
- p50 and p95 TTFT;
- p50 and p95 output tokens per second;
- prompt and completion tokens per minute;
- GPU memory, utilization, temperature, and power;
- queue depth and admission delay.

Increase load until the endpoint reaches its safe limit. The endpoint must
return `429` before requests exceed the queue-delay limit. Set the catalog
capacity at or below the repeatable measured result. Do not estimate capacity
from GPU specifications.

Do not use the direct-runtime benchmark as the external API result. The public
test must include TLS, the production gateway, authentication, admission,
billing, and the external network path.

## 10. Soak, restart, and drain

Run a representative load for 24 hours. During the run:

- record uptime, errors, TTFT, throughput, and `429` rates;
- confirm that memory use does not grow without bound;
- restart the model runtime once;
- drain the endpoint before the restart;
- confirm that readiness becomes false before shutdown;
- confirm that traffic resumes only after the model is ready;
- confirm that logs contain no prompts, completions, keys, or authorization
  headers;
- reconcile gateway token totals with runtime and billing totals.

A single-GPU deployment cannot provide uninterrupted service during its own
restart. Record that limitation. Do not claim high availability until a second
independent full replica passes the same tests.

## Result record

Record one summary without credentials or request content:

```text
Run UTC:
Endpoint:
Model ID:
Checkpoint revision:
Runtime and version:
GPU type and count:
Advertised context:
Advertised maximum output:
Catalog schema: PASS/FAIL
Authentication: PASS/FAIL
Non-streaming: PASS/FAIL
Streaming and final usage: PASS/FAIL
Stable errors: PASS/FAIL
Multi-turn: PASS/FAIL
Declared capabilities: PASS/FAIL
Cancellation: PASS/FAIL
Capacity result:
TTFT p50/p95:
Output TPS p50/p95:
24-hour soak: PASS/FAIL
Restart and drain: PASS/FAIL
Usage reconciliation: PASS/FAIL
Known limitations:
Decision: READY/NOT READY
```

Add the non-sensitive summary to the evidence log in
[`OPENROUTER_PROVIDER_README.md`](OPENROUTER_PROVIDER_README.md). Keep raw test
output under `.agents/runtime/` unless a reviewed result must become a durable
release artifact.

## Known limitations

- OpenRouter can change its private baseline tests without publishing the exact
  cases.
- This runbook does not test model quality or benchmark claims.
- Cancellation requires runtime telemetry for proof.
- Capacity and performance require a separate controlled load run.
- Optional feature checks must follow the exact capabilities published by the
  deployed catalog.

The next safe action is to keep the DeepSeek model at `is_ready: false`, run
this preflight, record the result, and enable OpenRouter staging only after all
required checks pass.
