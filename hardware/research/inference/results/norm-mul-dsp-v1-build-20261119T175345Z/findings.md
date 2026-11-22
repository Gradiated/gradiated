# Experiment 20 · Build qualification failed

Vivado stopped during project generation because the inherited compile audit required every supplied RTL unit to appear in the active hierarchy. The three RMSNorm instances no longer instantiate the unchanged generic fixed_scalar module, so Vivado omitted that file from the active compile order.

The saved build archive includes the available phase logs and checkpoints.

[Run record](run.json) · [Experiment 19 route](../ff-scalar-mul-dsp-v1-build-20261119T165358Z/findings.md)
