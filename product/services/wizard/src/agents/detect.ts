import { execFileSync } from "node:child_process";

export interface DetectedAgent {
  name: "opencode" | "codex" | "claude";
  found: boolean;
  version: string | null;
}

const AGENTS = ["opencode", "codex", "claude"] as const;

const detectOne = (name: (typeof AGENTS)[number]): DetectedAgent => {
  try {
    const output = execFileSync(name, ["--version"], {
      encoding: "utf8",
      timeout: 5_000,
      stdio: ["ignore", "pipe", "ignore"],
      // Windows resolves npm-installed agents to .cmd shims, which
      // execFileSync refuses to run without a shell. The command name is a
      // fixed literal, so this is not an injection vector.
      shell: process.platform === "win32",
    }).trim();
    return { name, found: true, version: output.split("\r\n")[0]?.split("\n")[0] ?? null };
  } catch {
    return { name, found: false, version: null };
  }
};

export const detectAgents = (): DetectedAgent[] => AGENTS.map(detectOne);
