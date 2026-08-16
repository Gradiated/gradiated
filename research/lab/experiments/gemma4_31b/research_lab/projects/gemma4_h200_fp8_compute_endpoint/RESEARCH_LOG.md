# Research log

## 2026-07-18 — bounded online E4M3 compute endpoint

Question: can the pinned SGLang runtime quantize the resident exact BF16 Gemma 4 31B checkpoint online to E4M3 compute, retain stock attention/FP8-E5M2 KV and the compatible c32 dynamic-chunked serving configuration, then earn the frozen 5% endpoint gate?

Action: claimed the warm H200, bound the stock comparator and exact-mix runner hashes, stopped only the c48 service, and tried the documented ModelOpt online producer. The first launcher omitted `--quantization modelopt_fp8` and failed its CLI contract; the single permitted repair added it. The repaired process reached the pinned runtime's executable compatibility guard before loading weights or serving. No stock arm, precision sweep, image pull, checkpoint transfer, custom attention mount, or offline export was run. The former c48 stock service was then restarted without replaying its workload.

Evidence (measured): the first container raises `ValueError: quantize_and_serve requires ModelOpt quantization`; the repaired `--quantization modelopt_fp8 --modelopt-quant fp8 --quantize-and-serve` path raises `NotImplementedError: quantize_and_serve functionality is currently disabled due to compatibility issues. Please use the separate quantize-then-deploy workflow.` Raw remote diagnostics, immutable input hashes, and the restored-server startup log are in `artifacts/20260718t1755z-online-e4m3-c32/`. `TERMINAL.json` is typed `unsupported`; no 32-row endpoint result exists because the pinned consumer rejects online production before server readiness. Conservative project-attributed exposure is $0.17, below the $1.10 reservation.

Interpretation: this is an implementation limitation of the pinned runtime's online producer, not a negative measurement of E4M3 compute or a quality claim. The separate export workflow is explicitly out of this project's one-online-producer scope, so this runtime path is closed.
