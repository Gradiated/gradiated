#pragma once

// Run one trusted runtime and reap its descendants before returning.
// This function owns process-wide signal handlers and Linux subreaper state.
// Call it once from the single-threaded launcher. It is not a sandbox.
int supervise(char *const argv[]);
