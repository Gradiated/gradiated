# TensorDock A40 lifecycle-adapter contract

## Question

Can the currently live TensorDock A40 venue be represented by a bounded, testable create/poll/delete adapter and durable ownership contract, leaving only explicit account/funding authority before an exact-load measurement?

## Why it matters

The alternate-venue screen found two live exact A40 hosts. The best screened path is online in Mölln at $0.3475/hour minimum configuration and $0.38225/hour after a 10% lifecycle allowance, requiring only 166.819 output tok/s for the 5% gate and 176.968 for $0.60/M. This is materially more attractive than L40S if load and throughput pass. The current barrier is not price discovery but an authenticated lifecycle adapter with exact host/GPU mapping, deletion, diagnostics, and durable cleanup semantics.

## Relevant evidence

- `a40_alternate_venue_verification/VENUE_SCREEN_2026-07-15.json`: two live A40 hostnodes; best exact hostnode, rate components, uptime, capacity signal, and terms.
- TensorDock's public console exposes host inventory and identifies `/api/session/deploy/single` as the deployment path, but no authenticated request or mutation has been attempted.
- Local NVMe is unreplicated and shared networking/ports require explicit artifact transfer, recovery, and cleanup handling.
- No TensorDock credential is currently exposed in the environment; this project must not manufacture authority or mutate the provider.

## Scope

Use one zero-cost researcher turn to pin the current official TensorDock web/API lifecycle contract needed for one exact A40 allocation: authentication/session mechanism, hostnode refresh, exact `a40-pcie-48gb` mapping, minimum CPU/RAM/storage/image/SSH/network fields, deploy request and response identity, provisioning poll/terminal states, direct instance lookup, deletion endpoint, billing/exposure fields, and inventory absence verification. Use only public documentation, unauthenticated responses, and static first-party console assets; do not log in, use credentials, fund an account, POST, reserve, or delete anything.

Implement a project-local provider adapter against a deterministic fake HTTP service or recorded schema fixtures. It must fail closed on changed host/rate/GPU mapping, duplicate ownership, missing resource ID, timeout, malformed response, and delete/inventory disagreement; retain bounded redacted diagnostics and produce typed terminals for successful fake lifecycle, create failure, deadline cleanup, and delete failure. Exercise the exact adapter/controller through an execution-equivalent `systemd --user` no-mutation/fake mode with canonical absolute paths and a durable watchdog. Keep secrets and browser/session state outside the repository.

Re-read the public A40 inventory at the end and report whether the exact host remains listed/online at an all-in screened rate <=$0.50/hour. Name the minimal external authority still required—account/session/token, funding cap, accepted terms, image/SSH setup—and the maximum safe future experiment cap. If public API semantics are too unstable or deletion cannot be bound, close TensorDock rather than proposing another adapter chain.

Do not run a real provider request, benchmark, model transfer, or quality test. Budget is $0 and this project owns no provider mutation.

## Available resources

Use the venue-screen artifact, official TensorDock console/API/static assets and terms, shared factory lifecycle primitives, the durable controller/watchdog patterns, and the current AWQ/A40 experiment contract.

## Portfolio-changing result

A passing fake/execution-equivalent lifecycle contract plus still-live <=$0.50/hour A40 inventory makes TensorDock the next measurement venue once explicit account/funding authority exists. Missing stable create/delete semantics, changed/absent capacity, or economics above the gate closes the provider path while leaving A40 performance unmeasured.
