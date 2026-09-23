import { join } from "node:path";

export const onWindows = process.platform === "win32";

export const OPENCODE_CONFIG = ".config/opencode/opencode.json";
export const OPENCODE_AUTH = ".local/share/opencode/auth.json";

export const CODEX_CONFIG = ".codex/config.toml";
export const CODEX_PROFILE = ".codex/gradiated.config.toml";

export const CLAUDE_BIN = ".gradiated/bin";
export const CLAUDE_COMMAND = join(
  CLAUDE_BIN,
  onWindows ? "claude-gradiated.cmd" : "claude-gradiated",
);
export const CLAUDE_SCRIPT = onWindows
  ? join(CLAUDE_BIN, "claude-gradiated.js")
  : CLAUDE_COMMAND;
