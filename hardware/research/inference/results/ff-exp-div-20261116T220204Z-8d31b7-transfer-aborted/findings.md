# Feed-forward comparison stopped during USB staging

The KV260 acknowledged all 5,174 indexed chunks, then rejected the reconstructed archive at its size or SHA-256 check. The host stopped before dispatch. Neither comparison circuit was loaded and the original circuit and weights were left in place. The board produced no inference, latency or energy results for this attempt.

The local archive still matches the independently reviewed 2,483,388-byte input and its expected SHA-256. An offline replay of the frozen receiver accepted the exact bytes and verified all 23 members. Replacing one Base64 character or dropping four reproduced the reported error after all chunks were acknowledged. The live receiver grouped size and hash failures together, so the archived evidence cannot identify which occurred or why.

[Run record](run.json) · [Exact RTL replay](../ff-exp-div-rtl-20261116T214222Z/findings.md) · [Routed build](../ff-exp-div-build-20261116T213813Z/findings.md) · [Experiment protocol](../../experiments/kv260-ff-exp-div-v1.md)
