import { execFileSync } from "node:child_process";

const ports = process.argv.slice(2).map(Number);

if (
  ports.length === 0 ||
  ports.some((port) => !Number.isInteger(port) || port < 1 || port > 65_535)
) {
  throw new Error("Pass one or more valid TCP ports.");
}

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

const isRunning = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error && typeof error === "object" && "code" in error) {
      if (error.code === "ESRCH") return false;
    }
    throw error;
  }
};

const wait = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

const listeners = [...new Set(ports.flatMap((port) => listenersForPort(port)))];

if (listeners.length > 0) {
  console.log(
    `Stopping stale development listeners on ports ${ports.join(", ")}...`,
  );
  listeners.forEach((pid) => process.kill(pid, "SIGTERM"));

  for (let attempt = 0; attempt < 15; attempt += 1) {
    if (!listeners.some(isRunning)) break;
    await wait(100);
  }

  listeners.filter(isRunning).forEach((pid) => process.kill(pid, "SIGKILL"));
}
