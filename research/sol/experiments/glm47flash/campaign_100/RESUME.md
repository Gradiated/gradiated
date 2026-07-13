# Campaign terminal state

Decision: `STOP_OR_PIVOT`.

Gate A passed, but Gate B did not. The Community and changed Secure A100 80 GB
PCIe requests both returned RunPod HTTP 500 before pod creation. Both cost $0,
the final inventory is empty, and the two-placement limit is exhausted. Do not
cycle through more best-effort A100 variants or return to the repeatedly failed
H100 placements.

Campaign-additional spend is $0.273464527, entirely from the earlier interrupted
L40S allocation. The two Phase-B requests added $0, leaving $99.726535473
unspent. Conservative account lifetime spend is $5.153606502. The final baseline
SHA-256 is `93434ba515f9695725924ed041719e1cfe8d8348fb52a5eddc3060bb4c87d878`.

No valid stock throughput/SLO result exists, so tuned, AWQ, paired quality,
custom-intervention, holdout, specificity, provider, and hardware claims remain
closed. The decision record is `DECISION_2026-07-13.json`.

The only named continuation is a placement pivot under fresh authorization: run
the same frozen 25-request stock BF16 harness once on a guaranteed or
provider-reserved 80 GB NVIDIA placement with the exact image pre-pulled. Run a
matched tuned control on that same machine only if stock passes. Do not build the
gateway.
