# Provider anchors — 2026-07-13

These are vendor-published price and product anchors, not matched benchmark results.
They must not be used to claim a cost, quality, latency, or throughput advantage for
the local GLM-4.7-Flash stack.

## Cloudflare Workers AI

- The official GLM-4.7-Flash model page lists a 131,072-token context window and a
  price of $0.06 per million input tokens and $0.40 per million output tokens.
- At the campaign's analytical 8:1 input:output ratio, this is $0.88 per million
  output-equivalent tokens (`0.40 + 8 * 0.06`), before any workload, quality, or SLO
  matching.
- Source: https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/

## Fireworks AI

- The official serverless pricing page lists GLM 4.7, not GLM-4.7-Flash, at $0.60
  per million input tokens, $0.30 per million cached input tokens, and $2.20 per
  million output tokens.
- The official pricing page lists on-demand H100/H200 capacity at $7/hour, B200 at
  $10/hour, and B300 at $12/hour.
- The official model page describes the listed model as GLM 4.7 (352B), not the
  GLM-4.7-Flash checkpoint under test.
- Sources:
  - https://docs.fireworks.ai/serverless/pricing
  - https://fireworks.ai/pricing
  - https://fireworks.ai/models/fireworks/glm-4p7

## Baseten

- The official library page provides a GLM-4.7-Flash deployment template described
  as optimized for low-latency inference on 2xH100. It is not a published managed
  Model API benchmark or a matched price/result pair.
- The official pricing page lists the GLM 4.7 Model API, not GLM-4.7-Flash, at $0.60
  per million input tokens, $0.12 per million cached input tokens, and $2.20 per
  million output tokens.
- The same pricing page lists dedicated A100 capacity at $0.06667/minute and H100
  capacity at $0.10833/minute (approximately $4.00/hour and $6.50/hour).
- Sources:
  - https://www.baseten.co/library/glm-4-7-flash/
  - https://www.baseten.co/pricing/
  - https://docs.baseten.co/inference/model-apis/overview

## Use in this campaign

- Cloudflare's GLM-4.7-Flash token prices are a vendor-claimed price anchor only;
  no matched quality, request geometry, concurrency, TTFT, TPOT, queueing, or
  failure-rate evidence has been obtained.
- Fireworks and Baseten GLM 4.7 serverless prices are not comparable model anchors.
- Fireworks and Baseten accelerator prices may inform analytical break-even
  calculations, but cannot substitute for an observed stock control on the same
  model, hardware, workload, quality gate, and SLO.
- Any future provider comparison must preserve the original response artifacts and
  use the same paired scorer and service-level acceptance policy as the local runs.
