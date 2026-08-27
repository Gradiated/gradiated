# Kimi K3 microarchitecture workload model

This experiment converts the released Kimi K3 text-model configuration into a
per-token operation, weight, state, and cache model.

Run it with:

```sh
cd research/sol/experiments/kimi_k3_microarchitecture
python3 -m unittest -v
python3 model.py
```

Open `results/report.html` after the run.

The report is an analytical screening result. It is not a B300, Vera Rubin,
FPGA, ASIC, power, or full-system measurement.
