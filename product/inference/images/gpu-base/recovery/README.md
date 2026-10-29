# Frozen recovery agent

These standard-library sources are a snapshot for the GPU base, separate from
the agent shipped in host bundles. They keep recovery and model management
available when no host bundle works. Normal host releases do not change them.
The recovery `ping`, `fence`, `claim`, and `configure` APIs and their disk state
remain supported by current controllers and host bundles indefinitely.

CI runs the host agent tests against this copy, so it stays compatible with
hosts that still run it. It is not copied into the GPU base image. Changing
system/CUDA compatibility requires a deliberate `base-id` change.
