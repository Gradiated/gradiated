export const AGENT_NAMES = ["opencode", "codex", "claude"] as const;

export type AgentName = (typeof AGENT_NAMES)[number];
