# Shared research tools

Small reusable scripts that help several projects may live here. Agents may also use model-specific tools in the campaign directory. Tools support researcher judgment; they do not define the research process.

The canonical GPU price data is [`../data/gpu_prices.json`](../data/gpu_prices.json). Validate and query it through `PYTHONPATH=research/factory/src python3 -m grad_research gpu-prices`; do not create project-local price tables.

The canonical hardware-capability data is [`../data/accelerator_inventory.json`](../data/accelerator_inventory.json). Query it through `PYTHONPATH=research/factory/src python3 -m grad_research accelerators` before building a model-specific chip dossier; add only measurements and facts that are absent or specific to the project.

`./grad-profile` is the shared GPU evidence tool. It captures profiler-off baselines, short Nsight or ROCm diagnostics, hashes compiler artifacts, normalizes traces/counters, compares $/token, and appends exact-shape measurements. Read [`../PROFILING.md`](../PROFILING.md) for commands. It never provisions provider resources.

`./lab-endpoint-pair`, `./lab-microscope`, `./lab-reproducer`, `./lab-kernel-eval`, `./lab-surgery`, `./lab-workspace`, and `./lab-tools` are optional scientific instruments. They standardize repeated evidence plumbing without prescribing experiment order or scientific conclusions. Read [`../SCIENTIFIC_TOOLS.md`](../SCIENTIFIC_TOOLS.md) and invoke only the tool needed by the current question.
