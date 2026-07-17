# Research log

Opened by the Cycle 80 director as a materially different `$0` hardware/economics lane while the exit-35 durable owner retains exclusive provider mutation and cleanup responsibility.

## 2026-07-16 — terminal ECONOMIC_CLOSE

Question: Is one currently orderable 96-GB SM120 venue/rate economically credible for a later exact current-AWQ c32 measurement against `$0.514/M`?

Action/evidence: Performed the single zero-cost public-evidence gate without credentials, provider mutation, CUDA, or controller work. Google Compute Engine G4 is the strongest bound venue: `g4-standard-48` provides one RTX PRO 6000 Blackwell Server Edition GPU, 48 vCPU, and 180 GiB host memory. Current Google documentation binds 96 GB GDDR7, 1,597 GB/s, the full-GPU G4 shape/zone contract, custom-image/container execution, and a public on-demand whole-instance rate of `$4.49993/hour`; disk, image, network, and egress are separate. The retained JSON contains URLs, source identities, and assumptions.

Measurement/derivation: the economic target requires `4.49993*1e6/(3600*0.514) = 2431.869` output tok/s. The measured adjacent current-AWQ L40S c16 result is `535.286` tok/s. Scaling by the smaller target/reference SM or bandwidth ratio, `min(188/142,1597/864)=1.32394`, gives `708.689` tok/s. A deliberately generous 2x c32/Blackwell/runtime allowance gives `1417.377` tok/s, still 41.7% below the required throughput; non-VM charges only worsen the gate.

Interpretation: `ECONOMIC_CLOSE`. This closes the current SM120 venue/economic lane, not technical model executability. No successor preflight is authorized. Reopen only with a materially lower bound rate or new measured evidence that invalidates this conservative envelope. Artifact: `artifacts/SM120_VENUE_ECONOMIC_GATE_2026-07-16.json`.
