# Kimi K3 architecture search

This is the first analytical/simulation rung for a model-specific but
open-model-flexible inference accelerator optimized for dollars per output
token rather than maximum speed. It binds Moonshot's released Kimi K3
checkpoint, reconstructs decode work and state from the public configuration
and model implementation, and compares tiled hierarchical-BSP machines with a
calibrated NVIDIA DGX B300 control and a current B300 cloud-price control.

The simulator is a falsification and ranking tool. Candidate performance,
energy, area, capex, and cost are scenario assumptions, not measurements or
tapeout evidence. It reports the custom-system capex break-even separately so
the design can be rejected when sourced package/BOM data arrive.

## Reproduce

```sh
python3 tensor_inventory.py --output evidence/tensor_inventory.json
python3 run_search.py --spec spec.json --output results/search_results.json
python3 -m unittest -v test_search.py
```

The inventory command reads only safetensors headers with HTTP range requests;
it never downloads the 1.56 TB checkpoint payload.
