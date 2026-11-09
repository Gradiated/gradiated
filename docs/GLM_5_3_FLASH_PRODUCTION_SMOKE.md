# GLM 5.3 Flash production agent smoke test

Date: 2026-08-27

Historical record: this run used the since-retired vLLM GLM runtime. GLM-5.3
Flash now serves on SGLang (`product/inference/bundles/glm-5-3-flash-sglang`).

## Scope

- Model: `z-ai/glm-5.3-flash`
- Model revision: `84c6a6aa9497188e15a635ba793b0f95a79b1033`
- Runtime revision: `vllm-933876c388fb129ad82590660e6506614559cb86`
- Client: OpenCode `1.18.23`
- API: production Chat Completions

## Result

The first agent run found a gateway tokenizer error on a tool continuation.
The gateway expected tool arguments as an object. OpenAI-compatible clients
send the arguments as a JSON string.

Commit `ec7a008e` converts the string to an object for local chat-template
rendering. It does not change the request sent to the runtime.

The final OpenCode run completed five model turns. It listed files, read two
files, edited one bug, ran `node --test`, and reported the result. The test
passed with one pass and no failures.

Measured usage for the successful run was 26,499 input tokens and 209 output
tokens. Derived cost was about `$0.00204` at the production prices. The run
completed in about 4.5 seconds.

Codex CLI was not tested against inference. Codex supports only the Responses
API for custom providers. The Gradiated Responses route currently returns 404.

## Run OpenCode

From the repository root, run:

```sh
./product/scripts/opencode-gradiated.sh
```

The launcher reads `OPENROUTER_API_KEY` from the approved AWS secret. It does
not store the key in the repository or the OpenCode configuration.
