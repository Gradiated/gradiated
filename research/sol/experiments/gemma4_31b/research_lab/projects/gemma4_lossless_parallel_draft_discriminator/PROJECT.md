# Gemma 4 lossless parallel-draft discriminator

## Question

Can one Gemma-specific causal forward propose several next-token candidates
whose verification preserves the exact target-model token and KV-commit
semantics while creating enough accepted c32 work to plausibly remove at
least 20% of the qualified endpoint cost?

## Why this matters

The campaign requires `0.500119281574996 s/request` or an equivalent
price-normalized result. Native NVFP4 placement is promising but remains one
hardware/representation lane. Lossless parallel drafting is materially
independent and can reduce target forwards without changing the served model
distribution when acceptance and rollback semantics are exact.

## Scope

- Reconstruct the exact local/global attention, position, target-logit,
  accepted-token, rejection, and KV-commit boundary for the pinned Gemma 4
  checkpoint and c32 workload.
- Inspect only the most relevant existing first-divergence capture and pinned
  runtime source needed to establish that boundary.
- Build one executable offline discriminator that compares ordinary target
  decoding with a bounded multi-candidate proposal/verification step and
  reports the first divergent token or KV state.
- Quantify the minimum accepted draft depth and verification cost required to
  clear the fixed 20% objective; reject a candidate that cannot meet that
  analytical hurdle before requesting GPU spend.
- Do not weaken target semantics, delete capacity, train an unbounded model,
  open another validator project, or claim endpoint speed from simulation.

## Immediate evidence path

Within 60 wall-clock minutes, persist a source-grounded causal chain and one
working exact-semantics discriminator on existing immutable inputs. It must
produce either a matching multi-token transition with an explicit hardware
measurement request, or a localized divergence that names the smallest
corrective code/dataflow change. Generic drafting plans and literature
summaries are not terminal results.

## Decision

Continue to a bounded target-hardware measurement only when exact semantics
hold and the accepted-work threshold can plausibly close a material fraction
of the campaign gap. Otherwise close only the tested proposal/commit recipe
and retain the causal localization.
