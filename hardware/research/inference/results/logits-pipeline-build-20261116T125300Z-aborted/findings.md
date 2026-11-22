# Token-score pipeline build stopped at source verification

Vivado rejected the build packet before project generation. Its runner still pinned the preceding transformer source. The candidate file matches the independently reviewed simulation, but the runner's separate Tcl source pin was stale. The initial package and failure archive remain pinned. The retry amendment updates that one source pin and verifies the other ten against the identical circuit files.

This attempt has no synthesis, timing, area or board result. [Failed run record](run.json)
