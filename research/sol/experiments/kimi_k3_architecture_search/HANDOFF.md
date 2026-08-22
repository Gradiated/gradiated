# Kimi K3 architecture-search handoff

Decision: advance only `streamtile_e12_economy` to cost sourcing and
measurement. It deliberately gives up maximum speed: at c128 it models 0.68x
the raw physical B300 throughput but 1.52x raw tokens/J, while satisfying the
chosen 85 ms / 1,500 tok/s speed floor. The transferred B300 calibration makes
it appear 1.13x faster; do not underwrite that cross-calibration.

At a synthetic $260k system target, the scenario gives $2.18 per million output
tokens at c128 versus $9.10 for eight secure-cloud B300s at $7.39/GPU-hour. The
candidate could cost up to $1.22M under the stated ownership assumptions before
losing to that cloud control. Neither number is an ASIC BOM or owned-B300 TCO.
The immediate gate is sourcing the 2.304 TB / 36 TB/s memory-package envelope;
then measure useful bandwidth and tile-group barrier loss.

Stopped lineages: the 64 TB/s StreamWeave point as the cost baseline,
compute-only scaling, SRAM above 144 MB/module, and heroic global fabric. A
faster 48 TB/s StreamTile point remains a sensitivity, not the selected design.

Resume:

```sh
cd /root/workspace/research/sol/experiments/kimi_k3_architecture_search
python3 -m unittest -v test_search.py
python3 run_search.py --spec spec.json --output results/search_results.json
```
