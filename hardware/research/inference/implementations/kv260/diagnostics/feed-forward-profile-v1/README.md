# Feed-forward cycle diagnostic

`replay.py` checks the adopted circuit, archived testbench and fixtures by hash, compiles the observation-only `monitor.svh` with the pinned simulator, then reruns the existing seven cases. `analyse.py` reads the raw counters, reconciles them with the exact adopted reference and emits case and position reports. See the [diagnostic protocol](../../../../experiments/kv260-feed-forward-profile-v1.md).

The activity-mask bits, from least to most significant, represent gate, up, down and scalar arithmetic occupancy. A dense engine is active in its operand read, MAC and rounding states. A scalar is active outside IDLE and OUTPUT during an accepted command's response wait. Raw arrays use the field widths and state order in `analyse.py`.

Use `python3 -B replay.py --help` for arguments. The destination must be a new directory on the Mac. The raw archive contains a pinned model and fixtures and belongs in ignored research runtime storage.
