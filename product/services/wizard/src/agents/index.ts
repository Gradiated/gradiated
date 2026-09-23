import type { AgentIntegration } from "./agent.js";
import { claude } from "./claude/index.js";
import { codex } from "./codex.js";
import { AGENT_NAMES, type AgentName } from "./names.js";
import { openCode } from "./opencode.js";

const AGENTS: Record<AgentName, AgentIntegration> = {
  opencode: openCode,
  codex,
  claude,
};

export const selectIntegrations = (
  agent: AgentName | undefined,
): AgentIntegration[] =>
  agent === undefined
    ? AGENT_NAMES.map((name) => AGENTS[name])
    : [AGENTS[agent]];

export const agentLabel = (agent: AgentName): string => AGENTS[agent].label;
