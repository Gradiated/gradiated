import { execFileSync } from "node:child_process";
import type { AgentName } from "./names.js";

export const isOnPath = (name: AgentName): boolean => {
  try {
    execFileSync(name, ["--version"], {
      timeout: 5_000,
      stdio: "ignore",
      // Windows resolves npm-installed agents to .cmd shims, which
      // execFileSync refuses to run without a shell. The command name is a
      // fixed literal, so this is not an injection vector.
      shell: process.platform === "win32",
    });
    return true;
  } catch {
    return false;
  }
};
