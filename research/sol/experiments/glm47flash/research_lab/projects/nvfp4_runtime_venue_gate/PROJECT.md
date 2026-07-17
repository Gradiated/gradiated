# NVFP4 runtime and venue gate

## Question

Does the current exact-model NVFP4 derivative have a technically runnable, quality-auditable path on commercially accessible Blackwell hardware with a conservative chance of beating the campaign's cost gates?

## Why it matters

The current external scan found `unsloth/GLM-4.7-Flash-NVFP4@98b036...`, including a separate MTP file, but no downloads, public quality result, throughput result, exact runtime recipe, or established Blackwell venue. NVFP4 is materially different from the active AWQ batching line and could change both memory traffic and viable hardware. A bounded GPU-free loader/venue falsifier is cheaper than ignoring it or attempting an unsupported paid launch.

## Relevant evidence

- `exact_model_external_scan/SCAN_2026-07-15.json` ranks NVFP4 third and explicitly parks it pending loader, quality, venue, and economics evidence.
- Official vLLM material covers exact-model BF16/FP8 and MTP paths but does not establish this derivative's NVFP4 execution.
- The campaign requires 8,192 input / 1,024 output, quality preservation, full lifecycle economics, and a matched >=5% gain; generic Blackwell marketing throughput is not transferable.

## Scope

In one zero-cost researcher turn, pin the exact derivative revision and perform a GPU-free source/config/manifest loader-capability check against one current pinned vLLM or SGLang revision that claims NVFP4 support. Download only metadata, configs, tokenizer, index, and small code files; do not download multi-gigabyte weights. Verify the exact GLM architecture mapping, quantization schema, tensor/index completeness, MTP relationship, required compute capability, and whether the runtime can construct the model/config path without silent fallback. Retain commands, revisions, bounded diagnostics, source identities, and a compact machine-readable result.

In parallel within the same turn, inspect current official provider catalogs or owned-hardware price sources for at least one actually orderable B100/B200/RTX Pro Blackwell-class measurement venue and one plausible production placement. Keep venue and production placement separate. Normalize credible hourly rates to the campaign gates by calculating required sustained output tok/s for <=$0.6365/M and <=$0.60/M, including stated storage/transfer/interruption/orchestration assumptions. Catalog price without readable capacity is a placement hypothesis, not availability.

Do not use credentials, create or reserve hardware, run a GPU benchmark, download the weight shards, modify the active AWQ project, revive the prior MTP project, or extrapolate performance from another model. Budget is $0 with no provider ownership. Stop after one runtime/config path and a bounded venue search.

## Available resources

Use official runtime repositories and documentation, exact Hugging Face metadata, official provider/hardware sources, the external-scan artifact, shared evidence tools, and `campaign_100` architecture evidence.

## Portfolio-changing result

Promote one later bounded Blackwell measurement only if the exact derivative has an explicit supported loader path, auditable checkpoint/MTP identity, a plausible quality-evidence route, an actually accessible measurement venue, and a conservative all-in break-even that could clear 5%. Unsupported format/architecture, silent fallback, absent quality route, or no credible venue/economics closes NVFP4 for this campaign as a useful negative result.
