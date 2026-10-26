# Security tools

## NanoGPT provider probe

`nanogpt_probe.py` sends public `PostHog/posthog-js` source review prompts through
GLM 5.3 Flash Uncensored. The purpose is to measure the client experience of each
provider under a small concurrency staircase, not to certify the reviewed SDK or
establish a provider's total capacity or long-term uptime.

It accepts only the public PostHog repository origin and verifies the selected
commit against GitHub's public PostHog commit API before reading fixed source
paths with `git show`. Local Git replacement objects are disabled. It never collects this repository's
product code. Keep the checkout and all results under ignored `.agents/runtime/`.
The NanoGPT key is read only from `NANOGPT_API_KEY`; it is never saved in results.
Do not put a key in a command argument or commit it.

```sh
git clone --depth 1 https://github.com/PostHog/posthog-js.git \
  .agents/runtime/nanogpt-review/posthog-js
git -C .agents/runtime/nanogpt-review/posthog-js rev-parse HEAD

# Use the full commit printed above. Prepare-only needs public GitHub access, but no API key.
python3 tools/security/nanogpt_probe.py \
  --repo .agents/runtime/nanogpt-review/posthog-js \
  --revision FULL_COMMIT \
  --output .agents/runtime/nanogpt-review/prepared --prepare-only

# Inject NANOGPT_API_KEY from an approved secret store into the process environment.
# This makes paid API requests. Each output directory must be new.
python3 tools/security/nanogpt_probe.py \
  --repo .agents/runtime/nanogpt-review/posthog-js \
  --revision FULL_COMMIT \
  --output .agents/runtime/nanogpt-review/run-01
```

Defaults: Auto, Arnict, Heabsy and Kitani; concurrency 1, 2, 4; 28 requests total;
1,536 output tokens/request; 90 seconds/request; 15 minutes/run. Every request
uses the same toolbar review packet; `--workload network` selects a larger packet
for a separate matched run. Additional levels 8 and 16 are supported, still with
at most 32 requests per run. `--cache-mode unique` places a distinct nonce first
in the system prompt for each request; verify provider-reported cached input
before describing a run as uncached. Default `shared` reuses the same prompt.
The conservative
cost reserve uses a UTF-8-byte input-token bound and twice the discovered rates.
The $1 local estimate limit is not a server-side spending guarantee. Set a key's
spending limit in NanoGPT as well when a hard billing limit is needed. HTTP
401/402/403 stops later phases. Requests are not automatically retried, so failures
remain visible. Provider pins use `only` and `allow_fallbacks: false`.

Results include the provider/pricing snapshot, public input hashes, run plan,
request metrics, candidate review responses and per-phase summary. The runner
reports first reasoning-or-content delta and first answer content separately.
TPS and TPOT are estimates from provider-reported completion usage and observed
SSE timing: chunks are not individual tokens. Auto's upstream provider cannot be
independently attributed from this API. Length-limited responses count as complete
transports and are flagged separately; they need not contain a useful review.
Repeated prefixes can use caches, so these are not verified cold-cache tests.

Each concurrency phase has only that many requests. Report counts, medians and
ranges; do not present those tiny samples as p95 reliability or saturation limits.
Source-review output is untrusted and requires separate local validation before
any security claim or disclosure.

Local checks:

```sh
python3 -m unittest discover -s tools/security -p 'test_nanogpt_probe.py' -v
python3 tools/devex/check.py
git diff --check
```

API contract: [provider selection](https://docs.nano-gpt.com/api-reference/miscellaneous/provider-selection).
