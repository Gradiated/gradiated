import { execFileSync, spawnSync } from "node:child_process";

import { forwardedListenPorts, stopListeners } from "./dev-ports.mjs";

const hostAlias = "gradiated-dev";

const ports = forwardedListenPorts(
  execFileSync("ssh", ["-G", hostAlias], { encoding: "utf8" }),
);

if (ports.length === 0) {
  console.error(
    `Add one or more LocalForward lines to the ${hostAlias} profile.`,
  );
  process.exit(64);
}

console.log(`Forwarding ports ${ports.join(", ")} at ${hostAlias}.test...`);
await stopListeners(ports);

const forwarder = spawnSync("ssh", ["-N", hostAlias], { stdio: "inherit" });

process.exitCode = forwarder.status ?? 1;
