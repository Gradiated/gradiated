# Launch-pipeline decision

Decision: nominate `single_packed_cpu_full_mask_staging` for one
checkpoint-free H100 falsifier. This is source-complete but unmeasured; it is
not an endpoint or fleet result.

Every director-bound hash matches. The exact v0.5.15 depth-12 chain is:
accepted-result visibility → CPU NGRAM corpus proposal → two small proposal
H2Ds → tree-index reconstruction → full attention-mask materialization → KV
slot assignment → dynamic metadata fill outside the graph → captured Gemma
hybrid target verification → sampling → accepted-KV move → asynchronous
result D2H → scheduler-owned KV/output/finish settlement.

The removable boundary is the full-mask construction in
`NGRAMWorker._prepare_for_speculative_decoding`. For each live row it creates
device ones, transfers a 12×12 mask, concatenates, casts to bool, and finally
concatenates all rows. This eager Python/CUDA fanout is outside the captured
target graph. The candidate packs the identical ragged bool layout in one
growable pinned CPU staging buffer and performs one H2D into a worker-owned
CUDA staging buffer. Tree reconstruction, attention metadata, global and
sliding attention, sampling, KV movement, result synchronization, scheduler
mutation order, graph padding, and request ownership do not change.

The CPU oracle passes bonus-only/zero-draft, partial, full depth-12, mixed-row,
padded-row, completion/later-settlement suppression, and slot-reuse cases. It also proves the packed mask is
byte-identical to the current layout. This is synthetic correctness evidence,
not execution readiness.

Source inspection does not provide H100 durations or verify steps/request, so
no finite positive endpoint reduction is claimed. The settled result must save
at least `13.394354 ms/request` (`1.89364%`) to cross average-rate stability
and `82.788318 ms/request` (`11.70428%`) to cross strict 90% headroom.

The smallest falsifier uses no checkpoint: on the exact pinned H100 runtime,
run stock and candidate depth-12 preparation at a mixed 32-row geometry,
consume both masks through actual Triton target-verify metadata plus one
Gemma-shape sliding and one global attention layer, require identical
producer/consumer outputs, benchmark 200 alternating warm repetitions, then
take one short Nsight Systems trace. Reject on any semantic difference, lack
of row-wise H2D/kernel reduction, a new sync/graph break, or non-positive
preparation-plus-consumer latency outside noise. Only a passing component may
advance to one unchanged c32 endpoint pair.

Canonical structured evidence is in `LAUNCH_PIPELINE_RESULT.json`; the
executable oracle is `launch_pipeline_oracle.py`.
