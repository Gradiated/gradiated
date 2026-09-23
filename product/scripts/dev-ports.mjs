import { execFileSync } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const listenPortPattern = /^(?:\[[^\]]*\]:)?(\d+)$/;

/** @param {string} sshConfig */
export const forwardedListenPorts = (sshConfig) => {
  const ports = sshConfig.split("\n").flatMap((line) => {
    const [keyword, listen = ""] = line.trim().split(/\s+/);
    const match =
      keyword === "localforward" ? listen.match(listenPortPattern) : null;

    return match ? [Number(match[1])] : [];
  });

  return [...new Set(ports)];
};

/**
 * lsof exits with status 1 when nothing matches; any other failure, such as a
 * missing lsof binary, must not pass for a free port.
 *
 * @param {unknown} error
 */
export const isNoListenersExit = (error) =>
  typeof error === "object" &&
  error !== null &&
  "status" in error &&
  error.status === 1;

/** @param {number} port */
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
    if (isNoListenersExit(error)) return [];

    throw error;
  }
};

/**
 * @param {number} pid
 * @param {NodeJS.Signals | 0} signal
 */
const signalProcess = (pid, signal) => {
  try {
    process.kill(pid, signal);
    return true;
  } catch (error) {
    if (
      typeof error === "object" &&
      error !== null &&
      "code" in error &&
      error.code === "ESRCH"
    ) {
      return false;
    }

    throw error;
  }
};

/** @param {number} pid */
const isRunning = (pid) => signalProcess(pid, 0);

/** @param {number[]} ports */
export const stopListeners = async (ports) => {
  const listeners = [...new Set(ports.flatMap(listenersForPort))];

  if (listeners.length === 0) return;

  console.log(`Stopping stale listeners on ports ${ports.join(", ")}...`);
  listeners.forEach((pid) => signalProcess(pid, "SIGTERM"));

  for (
    let attempt = 0;
    attempt < 15 && listeners.some(isRunning);
    attempt += 1
  ) {
    await sleep(100);
  }

  listeners.forEach((pid) => signalProcess(pid, "SIGKILL"));
};
