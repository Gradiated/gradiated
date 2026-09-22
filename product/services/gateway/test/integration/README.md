# Gateway runtime integration tests

CPU-only integration tests of the **actual Rust gateway process**, its HTTP
runtime client, and a disposable **real Valkey Cluster**. Kev and vLLM are
loopback HTTP servers, not replacements for the gateway's `ModelRuntime` trait.
No GPUs, model downloads, cloud credentials, or production endpoints are used.

```text
HTTP / official SDK -> real gateway -> scripted Kev or vLLM HTTP server
                            |
                            v
                 real Valkey admission + settlement
```

## Run and CI

From `product/` with Docker, Cargo and pnpm:

```sh
pnpm --filter @gradiated/gateway test:integration
# Narrow iteration, using the same infrastructure:
pnpm --filter @gradiated/gateway exec vitest run streaming
```

The `test:integration` script builds the Rust binary first; vitest on its own
intentionally does not build or download weights. The **Gateway runtime integration**
job builds the binary and runs this suite on every relevant PR and main push.
Failures fail CI; missing Docker/binary dependencies never silently skip tests.
The job uploads JUnit results. Add this check to branch protection when enforcing
merge gates; this change does not modify repository protection settings.

Each run creates an empty, uniquely labelled Valkey 8.1.9 container with all
cluster slots, random loopback ports and tmpfs storage. Ownership is checked
before seeding. Every case gets unique model, release, credential and tenant
identities. There is no configurable external Redis/runtime endpoint or flush.
Runtime controls live in the test process, never in customer request headers or
a deployed admin endpoint. The gateway child process receives an explicit
environment, so no ambient cloud or runtime credentials reach it; it gets a
generated test-only runtime secret and offline HF.
Fixtures stop processes and delete only their own container on normal success
or failure. SIGKILL/host loss can leave a container named `gateway-contract-*`;
inspect its matching `gateway-contract` label before removing that exact target.

Test files run in parallel against the one shared gateway and Valkey: every case
has its own tenant, model and runtime, and settlement reads filter by
organization. A new case must keep that isolation or the file must opt out.
Gateway deadlines are shortened to three seconds, prepaid concurrency to two;
prices are synthetic integer nano-USD. Tests have 30-second deadlines; CI has a
15-minute overall bound.

## Writing a test

`useCases()` gives a file a `makeCase`, a Valkey connection and cleanup between
tests. A case owns its own tenant, model, release and runtime replicas, so files
run in parallel without coordinating.

```ts
const { makeCase } = useCases();

const instance = await makeCase("vllm"); // one synthetic replica
const instance = await makeCase("kev", { replicas: 2 }); // two, for routing tests
```

Successful responses come from an **upstream**. The default is `synthetic`: the
wire profile in `mock-runtimes/` generates them, which is deterministic and
supports every fault. Point a case at a real server instead with `proxy`:

```ts
const instance = await makeCase("vllm", {
  upstream: { kind: "proxy", baseUrl },
  runtimeModel: model, // the id the real server serves, so substitution lands
});
```

Both upstreams record every forwarded request on `runtime.calls`, so assertions
about what the gateway put on the wire work either way. Faults are queued per
request with `runtime.enqueue({ ... })` — `status`, `fault`, `mutate`, `cached`,
`fragment`, `errorUsage`, and `gate` to hold a request open for concurrency
tests. Faults apply to proxied runtimes too, but a real server cannot be made to
emit a decreasing usage counter on command, so fault coverage stays synthetic.

## Real runtimes

Fidelity tests in `real-runtime.test.ts` run the gateway against one real LLM and
one real decision server on CPU, to catch drift between what the mocks pretend a
runtime does and what one actually does. They assert wire shape and that billing
settles from the runtime's own token counts — never exact token totals, because
real output length varies.

```sh
# Name the runtimes to start; anything unnamed stays synthetic and its tests skip.
GATEWAY_REAL_RUNTIME=vllm pnpm --filter @gradiated/gateway test:integration
GATEWAY_REAL_RUNTIME=vllm,kev pnpm --filter @gradiated/gateway test:integration
```

The LLM runtime is the CPU build of the same vLLM production runs, pinned by
digest, started with the wire-relevant flags copied from the production launch
script — `--scheduling-policy priority`, because that is what makes vLLM accept
the `priority` the gateway sends, and `--enable-prompt-tokens-details`, because
that is what makes it report the cached tokens the gateway bills on. Only the
sizing flags are scaled down.

Global setup starts each container, waits for readiness and removes it on the way
out, using the same ownership-checked cleanup as Valkey. Each runtime is
independently optional: if only one is available its tests run and the other
block skips. To use servers you already have running, set
`GATEWAY_REAL_RUNTIME_URL_VLLM` or `GATEWAY_REAL_RUNTIME_URL_KEV` and no container
is created. The vLLM CPU image is amd64-only, so on Apple Silicon use that
override or leave these tests to CI. Which images and models are used lives in one constant block in
`global-setup.ts`.

These are deliberately few. They are slow, they need multi-gigabyte images, and
they are not where edge cases belong — the synthetic suite owns those.

## Coverage and expectations

| Area             | Assertions                                                                                                                                                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity         | Missing/wrong/malformed/duplicate/expired/revoked keys; live revocation; bearer and x-api-key; archived/suspended/missing/inconsistent tenants                                                                                        |
| Qualification    | Exact public/private model mapping, normalized model IDs, cross-protocol rejection, bad JSON/duplicate keys, supported parameter bounds, Kev's default-only/non-streaming contract, request size, CORS                                |
| Admission        | Funded prepaid rejection, invoiced negative-balance serving, concurrent cap, independent tenants, no runtime calls or settlements before admission                                                                                    |
| Routing          | Session/state affinity, stale/unhealthy/busy/draining/revision-mismatched deployments, release isolation, alternate replica success, at most one retry, no retry after billed failure or stream output                                |
| Responses        | Choice/Noul/Score through TypeSafe SDK; text/tool calls through the chat SDK; private model rewriting; input/cache/output accounting; all chat tiers and exact prices                                                                 |
| Streaming        | SSE over arbitrary byte/UTF-8 boundaries, text/tool deltas, terminal usage and DONE ordering, missing usage/DONE, wrong model/ID/content type, decreasing usage, malformed events, partial disconnect, deadlines, client cancellation |
| Translation      | Chat, native SystemOne, Anthropic Messages and stateless Responses through real HTTP; translated streaming; stateful Responses rejection                                                                                              |
| Failure          | Runtime 400/401/429/500/503/redirect, oversized/malformed responses, transport disconnect, sanitized errors, post-failure recovery                                                                                                    |
| Financial safety | One event per generation, exact debit equals sum of charges, no leaked normal leases, correct terminal status, no success or debit on failed finalization                                                                             |

Every case checks gateway survival, unexpected mock contract errors, duplicate
settlements, final balance and admission cleanup. The finalization-failure test
explicitly asserts the deliberately retained expiring lease before cleaning up
its own tenant. Gateway policy maps runtime 429 **and 503** to public capacity
429; tests preserve that existing contract, not an assumed status passthrough.
Unknown unadvertised chat parameters are filtered according to existing gateway
policy; native SystemOne rejects unknown fields. Runtime usage, not the mock's
synthetic text length or a gateway tokenizer estimate, determines charges.

## Keeping mocks honest

- `mock_runtimes/kev.py` and `vllm.py` implement separate wire profiles; shared
  `server.py` supplies HTTP transport and scripted faults. They import no gateway
  parser, billing implementation, or production runtime adapter code.
- Tests assert requests reaching the actual socket: exact private model,
  priority, output limits, fields stripped by the gateway, and requested stream
  usage. Unexpected contract failures are recorded and fail fixture teardown.
- Official TypeSafe 0.7.0 and OpenAI Python 1.109.1 clients independently decode
  gateway responses. Mock self-checks also use the chat client's response types.
  Independent fixed expected usage/prices test accounting, rather than calling
  the gateway's pricing code to compute expected answers.
- The vLLM profile is **synthetic**, authored against the pinned
  [vLLM v0.10.2 OpenAI protocol](https://github.com/vllm-project/vllm/blob/v0.10.2/vllm/entrypoints/openai/protocol.py)
  (`ChatCompletionRequest`, response/chunk and usage structures). It represents
  the chat wire subset this gateway serves, not all vLLM options or versions.
  It assumes priority scheduling is enabled when exercising non-default tiers.
- Kev's profile is **synthetic**, following our pinned native adapter's wire
  contract. It reports scripted cache usage, not a simulated tokenizer/KV cache.
  Real cache correctness stays in the adapter tests and
  [real-GPU SDK suite](../../../../inference/runtimes/kev/E2E.md).
- On runtime/image upgrades, review the upstream wire changes and run the
  real-runtime suite as well. Add a minimal synthetic regression fixture for any
  incompatibility. Do not automatically rewrite expectations until tests pass.
  No real-vLLM deployment was exercised by this CPU suite; do not interpret its
  green status as a vLLM version/hardware certification.

## What green does not prove

This is a gateway data-plane integration suite. It seeds serving projections;
it does **not** test production registration, live health publishing, TLS/mTLS or
ingress configuration, IAM, PostgreSQL/ClickHouse settlement workers, distributed
Valkey failover, multi-gateway races, kernel correctness, tokenizer templates,
quantization, long-context memory pressure or sustained load/backpressure.
Existing Rust unit/Valkey tests remain complementary, including retrying
finalization and graceful-drain behavior. Real runtime tests and exact-target
qualification before rollout remain required. No production registration,
deployment, model price publication or GPU changes are made by this suite.
