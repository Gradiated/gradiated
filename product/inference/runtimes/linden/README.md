# linden-1 runtime

Native SystemOne serving for `gradiated/linden-1`, a 31B Gemma 4 decision model, behind the gateway's
`/v1/systemone` contract (`product/packages/contracts/src/systemone.ts`), the API the TypeSafe SDK calls.

- `service.py`: Kev's bounded ASGI adapter (`kev_http`) in front of a loopback SGLang 0.5.21 engine started from the
  pinned Hub revision (weights, configuration and tokenizer only; no repository code runs). The pinned
  revision is the FP8 checkpoint (compressed-tensors, FP8 dynamic: per-channel weight scales, per-token activation
  scales), which SGLang loads as FP8 from its config. It matches BF16 on Decision Index 0.3 (70.50 against 70.49 on
  11,025 questions) and is 21% faster on an 8,500-token request on a B300 (367 ms against 469). `LINDEN_QUANTIZATION`
  can still ask SGLang to quantize a BF16 revision on load.
- `prompt.py`: linden-1's prompt format and readout. The state becomes chat turns; each question is a block of
  lettered options; a request whose single read fits 3,000 tokens is written twice, and a longer one is read once
  after a header listing the questions. The answer is the softmax of the option labels' next-token log probabilities
  (score questions at temperature 0.6944). This is the format linden-1 was trained and evaluated with: on 8,510 real
  requests (21,900 questions) it renders byte-identical prompts to the reference implementation it was evaluated
  with.

## Request flow

Every question of a request shares the prompt up to its question block. When the whole request, with that prefix
repeated per question, fits 4,096 tokens, all questions go to SGLang in one batched pass (2-5 questions about a short
state take 48 ms on a B300 instead of 96 ms for prefix-then-questions). Larger requests prefill the shared prefix
first and then score every question against the cached prefix. Each call asks SGLang for one token and only the
option labels' log probabilities.

## Contract

- Questions: `noul`, `choice` (1-255 options; a single-option choice is answered without the model) and `score`
  (2-255 levels), up to 64 per request, any JSON in instructions and criteria. Text only: images, audio and files are
  rejected with 422.
- Answers carry exactly the gateway's fields: `noul`; `choice`, `confidence`, `probabilities`; `score`, `legend`
  (level index to description text), `confidence`, `probabilities`. Answers that would fail the gateway's checks mark
  the runtime unhealthy instead of being returned.
- Usage counts the request's distinct prompt tokens (the shared prefix once); output tokens are always 0.
- Prompts over 32,768 tokens get 422, never truncation. Up to 8 requests run at once; a ninth gets 429.

## Kernels

The bundle ships FlashInfer's prebuilt ops (`flashinfer-jit-cache`) and the TRT-LLM attention kernels SGLang uses for
Gemma 4 on B300 (`artifacts.json`, checksummed, seeded into FlashInfer's cache before every start), so a host never
compiles or downloads kernels.
