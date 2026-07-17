# Research log

## 2026-07-17 — typed arm packet, exact geometry, and rank

Question: can the paid owner start an identity-bound Gemma 4 MTP or async adjacent arm within ten minutes, and which later interaction deserves the next paid slot?

Action: inspected official target and assistant metadata without downloading weights, resolved current vLLM main/image identities, queried the shared H100 and price inventories, and checked the named shared lifecycle tools once. No provider or paid-project files were changed.

Measured evidence: target config `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` has 60 layers (50 sliding/10 full), hidden 5376, intermediate 21504, 32 heads, local 16 KV heads × 256, global 4 KV heads × 512, 1024 sliding window, vocab 262144, tied BF16 embeddings, and metadata total 32,682,372,656 parameters / 62,546,177,752 BF16 bytes. Assistant `google/gemma-4-31B-it-assistant@627c5ec1458b9086b841a91e0512fd31fd2fbbf1` is four layers, hidden 1024, intermediate 8192, and 939,042,560 BF16 bytes. Derived KV is 480 KiB/token unwindowed; resident KV is 0.712 GiB at 4,214 tokens and 1.154 GiB at 10K after local-window capping. Artifact hashes are recorded in `STATUS.json`.

Interpretation: the 62.55 GB target fits the 80 GB H100, while 50 MB L2 cannot retain weights. Decode is therefore provisionally weight-streaming/HBM and small-M scheduler limited; MTP is the first direct decode hypothesis and async scheduling the typed fallback. Current vLLM source/docs support native Gemma4 MTP depth 1, one-GPU BF16 placement, and async scheduling. MTP remains conditional on hashes, startup method=`mtp`, health, and exact greedy output identity; it must not delay stock. The top three are native MTP, async scheduling, and a matched MI300X placement screen ($2.60 committed planning vs $2.80 H100 SXM), with W4/FP8 and prefix caching closed for this cycle due missing execution-equivalent/quality evidence.

Next move: paid owner consumes `ADJACENT_ARM_PACKET.json`; run stock first, then MTP if its gate passes, otherwise async only if it can start within ten minutes. This project is complete at the offline evidence boundary; endpoint cost and quality remain unmeasured.
