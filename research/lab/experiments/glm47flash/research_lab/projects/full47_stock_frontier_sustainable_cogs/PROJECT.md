# Full-47 stock frontier sustainable COGS

## Question

Do the two exact full-47 stock c32 measurements, including the new maxseq36 robust point, support a defensible sustainable all-in operating envelope at or below the campaign's authoritative `$0.514/M` output-token target rather than only a productive-GPU steady-state pass?

## Why this matters

The first maxseq32 c32 run reached `596.851973` tok/s, leaving only about `0.4%` before non-GPU overhead at the `$1.10/hour` planning rate. The new maxseq36 session measures c32 at `609.606365` tok/s but c36 collapses to `549.798962` tok/s. The c32 point clears the `606.355` robust threshold, yet the session spent only `241.605` of `1,392.848` allocation seconds in scored profiles and was retained accidentally. A steady-state quotient is not yet a sustainable production claim.

## Scope

Work offline at `$0` for at most 900 seconds, 6 GiB RSS, and 32 MiB of new artifacts. Verify and consume the two immutable stock archives once:

- maxseq32 archive SHA-256 `ff873b597b33775787eada26ded437d1da91f326a47a8beb3ab8c994cc27cb4c`
- maxseq36 archive SHA-256 `ee558a30c26861960a6242788d056d1e898a5365bb908edc431e68765d2662f3`

Use the fresh shared `research/factory/data/gpu_prices.json` planning rate and range; do not search for prices. Separate measured, derived, and assumed terms. Reconcile c32 run-to-run throughput, c36 collapse, request completion/300-second background envelope, create/SSH/bootstrap/checkpoint/model-load/scored/retrieval/cleanup times, productive utilization, fixed storage and transfer, orchestration, retry/interruption sensitivity, queue fill, and session-length amortization.

For each valid c32 point, report steady-state planning COGS and solve:

- minimum productive fraction and minimum batches/session required to remain at or below `$0.514/M`;
- maximum interruption/retry plus lifecycle loss budget;
- sensitivity across the shared planning-rate range;
- exact-model market sensitivities at `$0.88/M` Cloudflare campaign mix and `$0.96/M` current non-reasoning Artificial Analysis campaign mix, while labeling `$0.568889/M` reasoning evidence variant-mismatched.

Do not transfer experiment-provider pricing into production COGS, call a provider, change a model/runtime, search externally, prepare a launch, or reopen prior lifecycle projects. Produce one compact machine-readable decision artifact and a concise log entry.

Return:

- `AUTHORITATIVE_SUSTAINABLE_PASS` only if an explicit conservative measured/derived operating envelope remains `<= $0.514/M`;
- `MARKET_ONLY_PASS` if the authoritative target fails but a named exact-model non-reasoning retail hurdle passes;
- `SUSTAINABLE_CLOSE` otherwise.

Every class remains quality-conditional. State whether the c32 run-to-run spread prevents treating `609.606365` tok/s as a sustainable denominator and whether a matched repetition would change the decision.

## Fixed evidence and gates

- Workload: exact cache-off 8,192 input / 1,024 output, complete requests, 300-second background envelope.
- Planning L40S rate: `$1.10/hour`; authoritative throughput/economic gates `594.466/606.355` tok/s.
- maxseq32 c32: `596.851973` tok/s.
- maxseq36 c32/c36: `609.606365/549.798962` tok/s.
- Full quality remains mandatory and unresolved.
