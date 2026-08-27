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
    }).trim();
    return { name, found: true, version: output.split("\n")[0] ?? null };
  } catch {
    return { name, found: false, version: null };
  }
};

export const detectAgents = (): DetectedAgent[] => AGENTS.map(detectOne);
