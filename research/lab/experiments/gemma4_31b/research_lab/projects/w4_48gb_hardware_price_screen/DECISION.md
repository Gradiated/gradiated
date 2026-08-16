# Decision: conditional RTX 6000 Ada nominee

Nominate the RTX 6000 Ada for one later matched-GPU measurement, conditional on the live L40S W4 mechanism passing. Its observed public on-demand rate is $0.77/GPU-hour, below the derived 10%-better all-in ceilings of $0.99/hour (a conservative 85% efficiency discount) and $1.10/hour (bandwidth-proportional prior). It matches the L40S's SM89, 142 SMs, 96-MB L2, 48-GB capacity, and pinned-source Marlin capability threshold; it has 11.1% more quoted bandwidth (960 vs. 864 GB/s).

This is not a throughput transfer or production claim. The sole required successor is a fresh, matched CUDA six-shape Marlin and c16/c32 whole-workload run, followed by a current written 12–24 month committed quote. Workstation cooling/sustained clocks and specialist-cloud host configuration can erase the nominal bandwidth edge.

Do not nominate A40 this cycle. Its $0.44/hour public rate needs only 44.4% of L40S whole-workload throughput for a 10% all-in improvement, but its SM86, 84 SMs, 6-MB L2, and 696 GB/s make the repeated W4 stream's occupancy/cache behavior too uncertain for the one nominee. It remains a price-sensitive fallback if RTX 6000 Ada availability or matched measurements fail.

Sources: shared fresh L40S committed planning rate ($1.10/hour), shared accelerator inventory, the pinned-vLLM source snapshots (minimum capability 75), and the public Ultralytics on-demand listing (A40 $0.44, RTX 6000 Ada $0.77, L40S $0.86/hour). The public listing is marketplace/vendor evidence, not a committed quote. Full arithmetic and labels are in `HARDWARE_SCREEN.json`.
