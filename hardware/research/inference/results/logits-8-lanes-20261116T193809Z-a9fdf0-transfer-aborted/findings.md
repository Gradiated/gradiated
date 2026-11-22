# Eight-lane test interrupted during serial transfer

The Mac entered idle sleep during the USB serial transfer. The sender stopped at 4,288 of 5,252 acknowledged chunks without a verified archive or launch receipt. Neither test circuit was loaded. No timing, energy or inference result was collected in this attempt.

The exact stop, serial receipts and sleep timestamps are retained. The recovery uses a fresh qualified packet with the same two circuit images and measurement protocol, and a process-scoped Mac sleep assertion during the transfer and run.

[Run record](run.json) · [Experiment protocol](../../experiments/kv260-logits-8-lanes-v1.md)
