#!/usr/bin/env node

import { execFileSync, spawnSync } from "node:child_process";

const hostAlias = "gradiated-dev";
const localHostname = `${hostAlias}.test`;

const portPattern = /^(?:\[?127\.0\.0\.1\]?):(\d+)$/;

const configuredPorts = execFileSync("ssh", ["-G", hostAlias], {
  encoding: "utf8",
})
  .split("\n")
  .map((line) => line.trim())
  .filter((line) => line.startsWith("localforward "))
  .map((line) => line.slice("localforward ".length).split(/\s+/)[1])
  .map((destination) => destination.match(portPattern))
  .filter(Boolean)
  .map((match) => Number(match[1]));

if (configuredPorts.length === 0) {
  console.error(
    `Add one or more LocalForward lines to the ${hostAlias} profile.`,
  );
  process.exit(64);
}

console.log(
  `Forwarding ports ${configuredPorts.join(", ")} at ${localHostname}...`,
);

const listenersForPort = (port) => {
  try {
    return execFileSync(
      "lsof",
      ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-t"],
      { encoding: "utf8" },
    )
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map(Number);
  } catch (error) {
    if (error && typeof error === "object" && "status" in error) return [];
    throw error;
  }
};

const listeners = [...new Set(configuredPorts.flatMap(listenersForPort))];

if (listeners.length > 0) {
  console.log(
    `Stopping stale listeners on local ports ${configuredPorts.join(", ")}...`,
  );
  for (const pid of listeners) process.kill(pid, "SIGTERM");
}

const forwarder = spawnSync("ssh", ["-N", hostAlias], { stdio: "inherit" });

process.exitCode = forwarder.status ?? 1;
