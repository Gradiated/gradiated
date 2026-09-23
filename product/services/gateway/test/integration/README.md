# Gateway integration tests

These tests run the real gateway binary against disposable dependencies. They
use only the CPU. They do not use GPUs, model downloads, cloud credentials or
production endpoints.

```text
HTTP client or official SDK
        |
        v
real gateway binary ----> loopback Kev or vLLM mock runtime
   |          |
   v          v
PostgreSQL   Valkey cluster
(tenants,    (admission, operational balance,
 catalog)     record cache, settlement stream)
```

## What the suite runs

- The gateway binary from `target/debug`. The test process gives it an explicit
  environment, so no ambient cloud or runtime credential reaches it.
- One PostgreSQL container. Global setup applies the product migrations, so the
  schema is the same one that the gateway queries.
- One Valkey container as a one-node cluster that holds all slots.
- Mock Kev and vLLM runtimes as HTTP servers on loopback ports. Each case starts
  its own runtimes.
- A closed loopback port as the Anthropic relay origin. A relayed request fails
  on the host and no test traffic leaves the host.

Each container has a random port, tmpfs storage and a `gateway-contract` label
with the run's owner name. Teardown removes only the containers whose label
matches. If a run is killed, a container named `gateway-contract-*` can stay.
Examine its label before you remove it.

The shared gateway has a three-second generation deadline, a concurrency cap
of two for each organization and a one-second record cache.
`gateway-process.ts` exports these settings. Tests derive their limits from
these constants.

## Layout

| Path                  | Contents                                                              |
| --------------------- | --------------------------------------------------------------------- |
| `global-setup.ts`     | Starts the stack, provides its URLs and tears it down.                |
| `stack/`              | Local Docker client, PostgreSQL, Valkey and the real CPU runtimes.    |
| `gateway-process.ts`  | Starts, waits for and stops one gateway process, and its settings.    |
| `case.ts`             | The `Case` fixture and `useCases`.                                    |
| `catalog.ts`          | The model, release and deployment records that a case publishes.      |
| `assertions.ts`       | Public error and propagation assertions.                              |
| `admission.ts`        | Gated requests that hold admission slots.                             |
| `chat.ts`             | The official chat client and checked stream chunks.                   |
| `mock-runtimes/`      | The Kev and vLLM wire profiles and the scripted fault server.         |
| `http-client.ts`      | A raw HTTP client for repeated headers, large bodies and cut streams. |
| `eventually.ts`       | Polling and timeouts.                                                 |
| `json.ts`, `ports.ts` | JSON guards and loopback port probes.                                 |
| `*.test.ts`           | One file for each gateway behavior area.                              |

## Run the suite

Run the commands from `product/`. You must have Docker, Cargo and pnpm.

```sh
pnpm --filter @gradiated/gateway test:integration
pnpm --filter @gradiated/gateway exec vitest run streaming
```

`test:integration` builds the gateway binary first. The second command does not
build the binary. A missing binary or Docker daemon fails the run. It does not
skip tests.

Docker must use a local unix socket. The suite refuses a remote Docker endpoint.

## Gateway logs

Each gateway process writes its log to
`<repository>/.agents/runtime/gateway-integration/`. Global setup clears this
directory at the start of a run. Teardown keeps it and prints its path.

## Write a case

`useCases()` gives a test file a `makeCase` function and checks each case after
each test. A case has its own organization, workspace, key, model, release and
runtimes. Thus test files can run in parallel.

```ts
const { makeCase } = useCases();

const instance = await makeCase("vllm");
const replicated = await makeCase("kev", { replicas: 2 });
```

The gateway reads tenants and models from PostgreSQL and caches them in Valkey.
Tests change rows, not the cache.

| Function                                       | Use                                                                       |
| ---------------------------------------------- | ------------------------------------------------------------------------- |
| `post(changes)`                                | Sends the default body for the case, with changes.                        |
| `setTenant(changes)`                           | Writes tenant rows and clears the cache, so the next request sees them.   |
| `writeTenantRows(changes)`                     | Writes tenant rows only. Use it to test cache expiry.                     |
| `setCredential(changes)`, `writeCredentialRow` | The same pair for the API key row.                                        |
| `recordBalanceTransaction(entry)`              | Adds a ledger entry.                                                      |
| `publish()`, `status(overrides)`               | Writes the model rows and the deployment status.                          |
| `settled(response, { status, charge })`        | Waits for one settlement and checks it.                                   |
| `expectNotDispatched()`                        | Checks that no runtime call and no settlement occurred.                   |
| `expectRejected(response, { code, param })`    | Checks the status, type and code of a public error and its generation ID. |
| `fillConcurrencyCap(instance)`                 | Holds requests open in the runtime until the organization cap is full.    |

After each test, the fixture checks that the mocks recorded no contract error,
that no admission lease stays, that each generation settled once and that the
balance equals the start balance less the charges.

### Runtime faults

`runtime.enqueue(options)` sets the result of the next request to that runtime.
The options are `status`, `fault`, `mutateBody`, `mutateEvents`, `cached`,
`fragment`, `errorUsage` and `gate`. A `gate` holds the request open until the
test releases it. If the request does not use an option, the mock records a
contract error. For example, a `stall` fault on a request that does not stream
fails the test. Test controls stay in the test process. They never use request
headers or an admin endpoint.

`runtime.calls` records each request that the gateway sent. Use it to check
what the gateway put on the wire.

## Real runtimes

`real-runtime.test.ts` runs the gateway against a real vLLM server and a real
Kev server on the CPU. These tests find differences between the mocks and the
real runtimes. They check wire shape and that billing uses the token counts
from the runtime. They do not check exact token counts.

```sh
GATEWAY_REAL_RUNTIME=vllm,kev pnpm --filter @gradiated/gateway test:integration
```

`GATEWAY_REAL_RUNTIME` names the runtimes to start. The tests for a runtime
that is not named are skipped. The images are built from
`product/inference/runtimes/{vllm,kev}/Dockerfile.cpu` with the weights
included. To use a server that already runs, set `GATEWAY_REAL_RUNTIME_URL_VLLM`
or `GATEWAY_REAL_RUNTIME_URL_KEV`. The vLLM CPU image is amd64 only. On Apple
Silicon, use the URL variable or let CI run these tests.

When a real runtime is enabled, global setup also starts a second gateway with a
120-second deadline for real CPU inference.

## Mock fidelity

- `mock-runtimes/kev.ts` and `vllm.ts` are separate synthetic wire profiles.
  They do not import gateway code.
- The vLLM profile builds its responses as the OpenAI client types, so `tsc`
  checks their shape.
- The official OpenAI and TypeSafe clients decode gateway responses in some
  tests.
- Expected charges are fixed numbers. The tests do not call gateway pricing
  code.
- When a runtime image changes, run the real-runtime tests. Add a synthetic
  test for each incompatibility that you find.

## What a green run does not prove

The relay origin must use HTTPS, so no local mock can stand in for the
provider. The suite tests a relay only as a refused connection. It does not
test provider error statuses or cut provider streams.

A green run does not test production registration, health publishing, TLS,
ingress, IAM, settlement workers, Valkey failover, races between gateways,
kernel correctness, tokenizer templates, long contexts or sustained load. The
Rust unit tests and the ignored Valkey tests are also necessary. A green run
does not certify a vLLM version or GPU type.
