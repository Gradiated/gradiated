#pragma once

#include <chrono>

inline constexpr std::chrono::seconds default_shutdown_grace{25};

// Returns only after every descendant has been reaped. It throws
// std::system_error only before the runtime starts. It changes the
// process-wide signal mask and subreaper state, so call it once from a
// single-threaded process. It is not a sandbox.
int supervise(char *const argv[], std::chrono::seconds grace);
