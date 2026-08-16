# GLM-4.7 Flash campaign conclusion

The user concluded this campaign on 2026-07-16 and selected Gemma 4 31B as the next target. The GLM harness was stopped and disabled before cutover, and a direct provider inventory check found zero instances and zero disks.

## Final measured position

- Exact stock endpoint: `609.606 tok/s`, approximately `$0.501/M output tokens` at the experiment's raw GPU-rate denominator.
- Selective-W4 endpoint: `630.195 tok/s`, approximately `$0.485/M output tokens`, but it did not pass the frozen development quality check.
- Top-3 shared-expert endpoint: `646.211 tok/s`, approximately `$0.473/M output tokens`, with 64/64 complete 8,192-input/1,024-output requests, but it also did not pass the frozen development quality check.

The campaign established a reusable autonomous experiment loop and several cost-mechanism results, but it did not produce a quality-qualified provider-beating endpoint. These results are model-scoped evidence, not assumptions for Gemma 4 31B.
