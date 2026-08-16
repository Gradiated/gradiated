# Research log

No researcher result yet. Compare a few joint expert-count/top-k geometries and return an executable cost proxy or falsifier, not a training plan or generic MoE survey.

## 2026-07-15 — Exact geometry screen: close without nomination

Question/action: can jointly reducing expert count and top-k create a conservative >=10% c16 L40S cost path? Added and ran `expert_count_geometry_proxy.py`, a stdlib-only executable that verifies the actual AWQ safetensors headers/index before deriving c16 routing, L2, parameter, FLOP, and group-M distributions for 64/4, 32/4, 16/4, and 16/2. It binds config `079f...fa7622b9`, index `b9c...bb988695`, and both retained decode traces; no provider or GPU was used.

Evidence: the checkpoint contains 47 sparse layers indexed 1..47 (3,008 routed experts, correcting the stale 46-layer wording), with 5,308,464 bytes/expert and packed `[1536,256]` gate/up plus `[2048,192]` down tensors. Layer routed weights are 324.003 MiB (64), 162.001 MiB (32), and 81.001 MiB (16); only 16 fits the L40S 96 MiB L2. At c16, 16/4 preserves 64 assignments and 1.208B active expert FLOP/layer but increases uniform expected rows per nonempty expert from 1.576 to 4.076 (2.58x) and cuts routed checkpoint bytes to 3.718 GiB. 16/2 halves active routed FLOPs, but even crediting half of the lowest retained fused-MoE (12.374%) and routing-sort (3.177%) summed trace work yields a 7.775% ceiling, below the required 9.955% endpoint wall-time cut / 594.466 tok/s gate.

Interpretation/next move: close this standalone route. L2 fit is a real chip-specific discontinuity, but 16/4 preserves FLOPs and current traces lack the L2/DRAM/occupancy counters required to turn it into a conservative endpoint prediction. Reopen only when a merged-and-retrained 16/4 checkpoint can be co-measured with another admitted L40S c16 architecture arm; retain expert-M, grid/block/register/shared/occupancy, L2 hit, DRAM bytes, and endpoint wall time, and reject it below 594.46 tok/s. Artifacts: `expert_count_geometry_bound.json` (`407094...4830e53b`) and proxy (`bc53cb...9cfa3e560`).
