# barge server

OpenAI-compatible HTTP layer over the barge engine (`barge serve`). The engine
runs on a dedicated OS thread (it owns the Metal device); axum handlers submit
requests over a std mpsc channel and read tokens back on per-request tokio
channels. Detokenization (incremental, TGI/vLLM prefix-window) and stop-string
matching happen server-side; the engine loop only ever sees token ids.

## Start

```sh
cargo build --release -p barge
./target/release/barge serve \
  --model models/smollm2-135m-instruct \
  --device metal --dtype f16 --port 8807
# knobs: --max-slots 64 --max-ctx 2048 --prefill-chunk 512 (defaults shown)
```

Startup runs one warmup request to absorb Metal pipeline compilation before
the listener accepts traffic.

## Endpoints

- `POST /v1/completions` — `prompt` (string), `max_tokens` (default 16),
  `temperature`, `top_p`, `top_k`, `seed`, `stop` (string or array), `stream`
- `POST /v1/chat/completions` — `messages` `[{role, content}]`, same params;
  `max_tokens` defaults to the remaining context budget
- `GET /v1/models` — single entry, id = model dir basename
- `GET /health`

### Non-streaming chat

```sh
curl -s http://127.0.0.1:8807/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":64,"temperature":0}'
```

Returns the standard `chat.completion` object with
`usage {prompt_tokens, completion_tokens, total_tokens}` and `finish_reason`
`stop` (EOS or stop string) or `length`.

### Streaming (SSE)

```sh
curl -sN http://127.0.0.1:8807/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":64,"temperature":0,"stream":true}'
```

Emits OpenAI `chat.completion.chunk` events: an initial role delta, one
content delta per detokenized piece, a final empty delta carrying
`finish_reason`, then `data: [DONE]`. `/v1/completions` streams
`text_completion` chunks with `choices[0].text`.

### Stop strings

```sh
curl -s http://127.0.0.1:8807/v1/completions -H 'Content-Type: application/json' \
  -d '{"prompt":"Count: one, two, three, four, five, six","max_tokens":64,"temperature":0,"stop":", nine"}'
# -> {"text":", seven, eight","finish_reason":"stop",...}
```

Matching is server-side: streamed text holds back `max(stop len) - 1` bytes so
a stop spanning chunk boundaries is still caught, output is cut at the first
match, and the response finishes with `stop`.

### Errors

```sh
# 400: prompt + max_tokens over the per-request context budget (--max-ctx)
curl -s http://127.0.0.1:8807/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":4096}'
# 400: n > 1 not supported (send concurrent requests instead)
curl -s http://127.0.0.1:8807/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"hi"}],"n":3}'
```

Both return OpenAI-style `{"error": {"message", "type"}}` bodies.

## Measurements (SmolLM2-135M-Instruct, f16, Metal, M4 Pro)

- Single request, server path end-to-end (`/v1/completions`, 128 tokens,
  short prompt, curl wall time, best of 3): **~114 tok/s** — decode at batch 1,
  so directly comparable to `barge gen` single-stream decode; HTTP + SSE adds
  no measurable overhead at this rate.
- 20 concurrent chat requests (64 max_tokens each): **20/20 completed** in
  1.72 s, 1119 completion tokens, **~650 completion tok/s aggregate** —
  continuous batching works through the server path.

## Caveats

- **No engine cancel yet.** When a stop string matches (or a client
  disconnects), the server drops its receiver and the engine keeps decoding
  the sequence to its max_tokens/EOS budget, discarding tokens. Wasted decode,
  never incorrect output.
- `n > 1`, logprobs, and penalties are not supported (engine keeps sampling
  minimal by design); `n > 1` is rejected with a 400.
- Chat templating is the hardcoded per-family table (`ChatTemplate::detect`):
  ChatML when `tokenizer_config.json` mentions `im_start`, plain concatenation
  otherwise. No system-prompt injection beyond what the client sends.
- EOS token ids are filtered from output text server-side (the engine emits
  the EOS token before `Done`; without filtering, ChatML models would leak
  `<|im_end|>`).
- Without an explicit `seed` the server draws one per request, so repeated
  identical requests differ at `temperature > 0`; pass `seed` (and
  `temperature: 0` for greedy) for reproducibility.
- Requests are admitted FCFS with no queue bound; a burst larger than the slot
  count simply waits inside the engine's queue.
