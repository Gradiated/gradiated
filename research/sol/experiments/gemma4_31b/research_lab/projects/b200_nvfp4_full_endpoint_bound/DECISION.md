# Decision: close B200 full stack

Terminal: `close_b200_fullstack`.

At c128 the price-normalized B200 hurdle is `38.134820` batch seconds (`0.2979282812 s/request`), and reopening the direct falsifier requires 20% headroom: `30.507856` seconds (`0.2383426250 s/request`).

The closure-safe impossible bound is already `43.691286` seconds. It gives B200 more credit than an executable stack: the complete `149.189555` seconds through the last TTFT is free, all measured decode-linear time is free, and the actual FP8-KV attention stack plus tied BF16 head each receive the full `2.38806x` HBM ratio. It still misses economics by `5.556466` seconds and the reopen gate by `13.183430` seconds.

The pinned-source optimistic bound adds the ideal c32 SM100 NVFP4 prefill-plus-decode floor and reaches `49.727324` seconds. The pinned vLLM commit supports a common FP8-KV Triton route for Gemma's local `d256` and global `d512` attention on SM100. FlashInfer is prioritized on SM100 but only advertises head sizes through 256, so global `d512` cannot be assigned a Blackwell FlashInfer speedup at this revision.

Even after free queue/prefill, ideal NVFP4 linears, and ideal bandwidth scaling of attention and head, reopening would require a separate `19.219468`-second reduction—`53.03%` of the remaining algebraic service/non-linear tail. The staged 24-row component test cannot measure or supply that intervention. Do not reopen it and do not spend on a B200 venue.

Sensitivity: granting that unattributed tail the full `2.38806x` ratio as well produces `28.662102` seconds and would pass the reopen threshold. This is intentionally not admitted: endpoint telemetry does not partition the tail into model-forward kernels, and the pinned mechanism supplies no exact representation, dispatch, or achieved bound for norms, activations, rotary, sampling, and service/runtime work. It is a separate unsupported full-stack intervention, not evidence for the staged linear-component test.

Canonical evidence: `FULLSTACK_BOUND.json` (`sha256:7ff6571e8cdb365928db6e065d732454c3c3da5b6c7968713abc467dcb1a1565`), reproduced by `python3 fullstack_bound.py --verify-upstream`.
