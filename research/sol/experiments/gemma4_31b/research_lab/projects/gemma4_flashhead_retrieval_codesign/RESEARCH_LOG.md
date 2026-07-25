# Research log

## 2026-07-25 — project admitted

The director admitted an independent deep lane for a sublinear
large-vocabulary head. It is distinct from the active exact grouped LM-head
kernel: this project may change the output-head architecture and initially
measures recall, target-decision divergence, and physical cost rather than
requiring exact dense logits.

## 2026-07-25 — balanced retrieval simulator and structural falsifier

- **Question:** Can a training-free balanced embedding index recover the tied head's target decisions with more physical upside than dense 12xM32 and the ideal grouped-exact lane?
- **Action:** Bound the exact SGLang producer/consumer and 180-call H200 attribution, then implemented `clustered_retrieval_sim.py`. It builds leakage-free balanced hierarchical 2-means indexes over 32-D and 128-D fixed projections of the exact 262144x5376 tied embedding, scores exact original-space centroids and candidate tokens, and reports top-1, top-10, verifier-decision recall, bytes, FLOPs, launches, and H200 roofline cost.
- **Evidence:** The only persisted 32-row actual-consumer hidden fixture has one unique row, so its apparent perfect recall was preserved as an invalid attempt. On two deterministic diverse structural proxies, the best common 128-D configuration below the ideal grouped-exact `1093.817 us` floor uses 2048 clusters x 16 probes (2048 candidates) but reaches only `34.375%/37.5%` top-1 and `34.063%/14.375%` top-10 recall. Even the 32-D sweep's highest mixture recall is only `84.375%` after scoring 32768 tokens, at a `6132.531 us` floor. See `artifacts/offline-clustered-retrieval-20260725/DECISION.json`.
- **Interpretation:** Close this static balanced-centroid realization. Routing recall is the first limiter; high probes then lose the grouped-exact advantage to candidate-cluster HBM traffic. This does not reject learned/frequency-aware FlashHead routing or post-training, and no quality or sampling claim was made.
- **Next:** Do not claim a GPU for this index. The smallest useful capture is one unseen 384-row target-verification step with proposed draft IDs, dense top-10, request/depth mapping, and accepted-prefix decisions (~4.2 MB). Resume only with that capture plus a learned or frequency-aware router that first clears 31/32 top-1 and 90% top-10 offline while remaining below the grouped-exact floor.
