# Kev native runtime adapter

Private ASGI runtime for the Rust gateway's native `POST /v1/systemone` dispatch.
Serves exactly `jaredpalmer/kev-9b`; no aliases, autoregressive generation,
fallback model, public tier selection, registry changes, or production reporter.
The gateway deployment runtime release must declare `protocol: "system_one"` to
select dispatch.

## Interface and bounds

- `POST /v1/systemone`: required `model`, `state`, `questions`; optional integer
  `priority` in `{-10, 0, 10}` (default `0`). Gateway currently sends `priority:0`.
  Priority is validated but does not schedule work: there is no inference queue.
  `state` must be a string, object, or array; scalar numbers, booleans and null
  are rejected before inference.
- Upstream `choice`, `noul`, and `score` inputs and answers are preserved.
  Reject unknown top-level/question fields, duplicate JSON keys, nonfinite
  numbers, unsupported model IDs and ignored noul criteria names.
- 1–64 questions, question keys 1–200 characters, JSON depth at most 32,
  body at most **1 MiB**, including streamed/chunked bodies. Gateway's 32 MiB
  limit is intentionally looser. Body receipt has a 15-second deadline.
- Upstream `model.encode(..., strict=True)` enforces 8,192 state tokens and
  8,192 **state-plus-question** tokens, including delimiter and option tokens.
  Also cap the packed input and `question_count * (state + longest_branch)`
  at 8,192 tokens. The latter bounds hybrid padded-row allocations; a request
  with many individually valid questions can therefore receive 422.
- `usage.input_tokens = len(encoded.ids)` (state counted once, all branches
  included). `cached_input_tokens` is exactly the encoded state-prefix length
  on a successful hit, otherwise zero. **`output_tokens = 0`**, including when
  the answer JSON is large. `latency_ms` measures synchronized model execution.
- Four-entry LRU, eligible from 384 state tokens including the delimiter.
  Keys are exact prefix token IDs plus option isolation. Upstream owns hybrid
  recurrent/conv and attention cache operations. Errors clear the cache.
- One admitted request per process/GPU, acquired before reading its body;
  concurrent requests immediately receive **429** with `Retry-After: 1`.
  HTTP cancellation does not release admission until the worker and GPU finish.
  Health remains responsive. Shutdown drains outstanding inference.
- `GET /health`: 200 after model loading; `GET /v1/models` returns
  `{"models":[{"id":"jaredpalmer/kev-9b"}]}` (runtime metadata, not the SDK
  catalog schema). Optional bearer authentication applies to **all** routes.
  Token comparisons use constant-time fixed-length SHA-256 digest comparison.
  Errors use `{"error":{"message":"..."}}`; inference errors never expose
  exceptions or model payloads. Invalid inputs are 422, body overflow 413,
  missing/wrong content type 415, authentication failure 401.

## Start on the existing prepared GPU environment

Requires Python 3.12+, the existing frozen upstream serving dependencies and
Uvicorn. No install or process restart is performed by these files. Keep the
upstream source checkout clean at
`f0ae8fb9af5762254974dcdba8c82cbf48587b2e`; startup verifies its Git commit.
`Checkpoint` loads the exact adapter revision
`2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c` and verifies the base is
`Qwen/Qwen3.5-9B-Base@68c46c4b3498877f3ef123c856ecfde50c39f404`.
It uses explicit BF16 `LoadOptions` with checkpoint calibration and upstream
defaults; serving environment overrides for temperature, date preprocessing,
prefix capacity and fallback models do not change this adapter's behavior.

Launch **one process per GPU**, never multiple Uvicorn workers. GPU isolation
is the launcher's responsibility; startup requires exactly one visible GPU.
From the repository root, using the existing Kev environment's Python:

```sh
CUDA_VISIBLE_DEVICES=0 /workspace/kev/.venv/bin/python \
  product/inference/runtimes/kev/adapter.py --port 8009 \
  --token-file /run/secrets/kev-runtime-token
```

Use `CUDA_VISIBLE_DEVICES=1 --port 8010` for the second replica (same command,
with those two values changed). Bind defaults to `127.0.0.1`; `--host` is an
explicit override. The token file is optional, external to version control,
and read at startup; it must contain 16–4096 printable non-space ASCII bytes
with an optional final newline. Gateway sends `Authorization: Bearer <token>`.
Keep an unauthenticated runtime reachable only by the trusted gateway. There
is no adapter hard GPU timeout: hung work retains the slot; the process owner
must recover the worker. Uvicorn bounds HTTP concurrency at 64, separately
from the single inference slot.

## Verification

CPU-only unit tests use a character tokenizer and in-process probability/cache
stub. By default, API/encoder doubles in `test_support.py` need only
the Python standard library. With `KEV_SOURCE=/path/to/kev-source`, the
same tests exercise its API and pure encoder functions (requires Pydantic,
included in FastAPI). Encoder functions are loaded from its AST to avoid
importing Torch or Transformers. Set `KEV_SOURCE` if the checkout is elsewhere.
No test installs dependencies or downloads weights. CI can use only
`fastapi`, `httpx`, and `pytest` and run `pytest` on this directory.

```sh
PYTHONDONTWRITEBYTECODE=1 tools/browser/.venv/bin/python -m unittest discover \
  -s product/inference/runtimes/kev -v
```

Exact CPU CI command (no Torch, Kev, SDK, or model download):

```sh
PYTHONDONTWRITEBYTECODE=1 uv run --no-project --python 3.12 \
  --with fastapi --with httpx --with pytest \
  python -m pytest -p no:cacheprovider product/inference/runtimes/kev -q
```

These CPU tests do not validate GPU kernels, weights, or Rust/Valkey integration.
See [E2E.md](E2E.md) for the shared official TypeSafe SDK suite in
`product/scripts/test-kev-gateway.test.ts`, its isolated gateway setup, and live
verification commands. This is the single SDK E2E test path.
