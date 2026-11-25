---
name: internal-ai-gateway
description: Internal Gradiated skill for calling Gemini, Anthropic, and OpenAI models through the tailnet Internal AI Gateway (http://internal-ai-gateway.tail186117.ts.net:8317). Use for internal evaluations, LLM judges, benchmarks, and research or development scripts on authorized Gradiated tailnet machines.
---

# Internal AI Gateway

> **Internal skill:** For Gradiated internal engineering, research, and evaluation workflows on the Gradiated tailnet. Not for customer-facing production inference.

Use the Internal AI Gateway to call **Gemini**, **Anthropic**, and **OpenAI** models from any authorized machine on the Gradiated tailnet (team workstations, dev machines, and dev-training GPU VMs).

## Connection details

- **Base URL:** `http://internal-ai-gateway.tail186117.ts.net:8317` (or `INTERNAL_AI_GATEWAY_BASE_URL` from `.env`).
- **API key:** `INTERNAL_AI_GATEWAY_API_KEY` in `.env` (populated via `gradctl env build` from `gradiated/dev/env`). Never print, log, or commit the key.
- **Auth header:** `Authorization: Bearer <INTERNAL_AI_GATEWAY_API_KEY>`
- **Network requirement:** Connected to the Gradiated tailnet (`gradctl tailnet status`).

## Supported providers and endpoints

The gateway routes requests across **Gemini**, **Anthropic**, and **OpenAI** models using standard API formats:

- `GET /v1/models` — list currently available model IDs across all providers.
- `POST /v1/chat/completions` — OpenAI-compatible Chat Completions API (works across OpenAI, Anthropic, and Gemini models; supports `reasoning_effort`, `response_format`, `max_completion_tokens`, and streaming).
- `POST /v1/responses` — OpenAI Responses API.
- `POST /v1/messages` — Anthropic Messages API.

Always query `GET /v1/models` to verify exact model IDs before launching a batch job.

## Quick check (list live models)

```python
import json, os, urllib.request

base = os.environ.get("INTERNAL_AI_GATEWAY_BASE_URL", "http://internal-ai-gateway.tail186117.ts.net:8317")
key = os.environ["INTERNAL_AI_GATEWAY_API_KEY"]

req = urllib.request.Request(f"{base}/v1/models", headers={"Authorization": f"Bearer {key}"})
with urllib.request.urlopen(req, timeout=10) as resp:
    models = sorted(m["id"] for m in json.loads(resp.read())["data"])
print(len(models), models)
```

## Example call (OpenAI SDK)

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ.get("INTERNAL_AI_GATEWAY_BASE_URL", "http://internal-ai-gateway.tail186117.ts.net:8317") + "/v1",
    api_key=os.environ["INTERNAL_AI_GATEWAY_API_KEY"],
)

resp = client.chat.completions.create(
    model="<model-id-from-/v1/models>",
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)
```

## Operational guidelines

1. **Use bounded concurrency with retries:** cap in-flight requests at ~8–12 concurrent workers per script and retry `429` / `5xx` responses with exponential backoff and jitter.
2. **Keep credentials out of logs and commits:** read `INTERNAL_AI_GATEWAY_API_KEY` from `.env` or environment variables; never hardcode or print it.
3. **Internal use only:** this endpoint is tailnet-private and intended for internal development, evaluation, and research workloads rather than customer-facing traffic.
