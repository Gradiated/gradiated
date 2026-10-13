# Frozen recovery agent

These standard-library sources are a snapshot for the GPU base, separate from
the agent shipped in host bundles. They keep recovery and model management
available when no host bundle works. Normal host releases do not change them.
The recovery `ping`, `fence`, `claim`, and `configure` APIs and their disk state
remain supported by current controllers and host bundles indefinitely.

For a deliberate base update, run `python3 tools/gpu/refresh-recovery.py`, review
the source changes, and qualify the base image before separately pinning it.
The base supplies `desmondd` beside this code. Changing system/CUDA compatibility
also requires a deliberate `base-id` change.
