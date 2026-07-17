# Research log

## 2026-07-17 — director delegation

Activated as the sole paid lane after the BF16 H200 launcher closed pre-science. Use the proven shared L40S vLLM lifecycle and resident exact checkpoint for one online-FP8 semantic-first endpoint falsifier. Budgets: 110 wall minutes, 80 provider minutes, 1.34 L40S-hours, 3 CPU-hours, one 200-GiB disk, 12 GiB artifacts, and `$2.00`; one allocation. The only same-session follow-up is prefix cache on/off after the named prefill/raw-metric/readiness trigger.

## 2026-07-17 — terminal pre-provider owner-initialization failure

Question: launch the single semantic-first exact Gemma online-FP8 L40S owner. Action: consumed the passing identity terminal, bound the image/checkpoint/trace/economic inputs in `FINAL_PROGRAM_AUDIT.json`, corrected per-primary-arm persistence, and started `gemma-l40s-fp8-20260717t091500z-owner.service`. Evidence: systemd captured `FileNotFoundError` while the owner tried to create `artifacts/gemma-l40s-fp8-20260717t091500z`; the artifact parent did not exist. The exception happened before inventory/create, so no instance, disk, watchdog, checkpoint transfer, model load, request, or useful GPU time exists. Interpretation: this is a typed local owner-initialization failure, not online-FP8, L40S, or endpoint evidence. The one-allocation/pre-science stop rule prohibits a repair/retry. Next move: none; preserve the diagnostic for director reallocation.

## 2026-07-17 — director admits one no-provider initialization correction

The terminal did not consume the one allocation or any provider budget. Reopen in place for exactly one local correction: create only the artifacts parent, preserve a distinct nonexistent owner output directory, and strengthen the final-program audit to the full brief before any create. This is not a provider retry and does not expand the original limits. A later pre-science failure after provider creation closes without another correction.

## 2026-07-17 — durable L40S owner launched

Question: execute the one semantic-first online-FP8 L40S allocation after the no-provider correction. Action: created only the artifacts parent, emitted passing `full_contract_final_program_terminal` (23 checks), refreshed authenticated empty inventory, and launched `gemma-l40s-fp8-20260717t092300z-owner.service`. Evidence: systemd owner PID `1964299` is active in its recorded cgroup; create returned `0` for RUNNING `computeinstance-e00zxg0g6arqy4f1bb` (`gpu-l40s-a`, 200-GiB disk `computedisk-e00v43naz2bravkavh`); independent watchdog `gemma-l40s-fp8-20260717t092300z-watchdog.service` PID `1964478` is active through deadline epoch `1784286172.7756126`. Interpretation: provider execution is now retained under the sole authorized owner, progressing from create to SSH/bootstrap/transfer. Next move: reconcile only its typed terminal; do not create, poll, or mutate another allocation.

## 2026-07-17 — bootstrap terminal; online-FP8 L40S lineage closed

The exact image downloaded and its digest verified, but the bootstrap invoked `docker run IMAGE nvidia-smi ...` without overriding the image's `vllm` entrypoint. The container therefore parsed `nvidia-smi` flags as vLLM CLI arguments and exited before checkpoint transfer, model load, semantic request, or useful GPU work. Cleanup passed with zero instances/disks after 389.732 provider seconds; derived experiment cost was `$0.093952`. Per the one-allocation/no-paid-repair rule, close. This is an entrypoint/launcher result only and provides no online-FP8, L40S, quality, throughput, or economic evidence.
