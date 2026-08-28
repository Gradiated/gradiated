export const DEFAULT_API_BASE_URL = "https://api.gradiated.com";
export const INFERENCE_BASE_URL = "https://api.gradiated.com";
export const CONSOLE_URL = "https://console.gradiated.com";

export type AgentName = "opencode" | "codex" | "claude";

export interface Options {
  apiBaseUrl: string;
  inferenceBaseUrl: string;
  yes: boolean;
  dryRun: boolean;
  model: string | undefined;
  key: string | undefined;
  agent: AgentName | undefined;
  agents: readonly AgentName[];
  mode: "auto" | "signup" | "login";
}

export interface ParsedArguments {
  command: "install" | "uninstall" | "help" | "version";
  options: Options;
}

function argumentValue(
  arguments_: readonly string[],
  flag: string,
): string | undefined {
  const index = arguments_.indexOf(flag);
  return index >= 0 ? (arguments_[index + 1] ?? undefined) : undefined;
}

function hasFlag(arguments_: readonly string[], flag: string): boolean {
  return arguments_.includes(flag);
}

export function parseArguments(argv: readonly string[]): ParsedArguments {
  const positional = argv.filter((argument) => !argument.startsWith("--"));
  const first = positional[0];
  const command =
    first === "uninstall"
      ? "uninstall"
      : first === "help" || hasFlag(argv, "--help")
        ? "help"
        : hasFlag(argv, "--version")
          ? "version"
          : "install";

  const mode = hasFlag(argv, "--signup")
    ? "signup"
    : hasFlag(argv, "--login")
      ? "login"
      : "auto";

  const apiBaseUrl =
    argumentValue(argv, "--api-base-url") ?? DEFAULT_API_BASE_URL;
  const requestedAgent = argumentValue(argv, "--agent");
  if (
    requestedAgent !== undefined &&
    requestedAgent !== "opencode" &&
    requestedAgent !== "codex" &&
    requestedAgent !== "claude"
  ) {
    throw new Error(
      `Unsupported agent "${requestedAgent}". Use "opencode", "codex", or "claude".`,
    );
  }

  return {
    command,
    options: {
      apiBaseUrl,
      inferenceBaseUrl: apiBaseUrl.replace(/\/$/, ""),
      yes: hasFlag(argv, "--yes"),
      dryRun: hasFlag(argv, "--dry-run"),
      model: argumentValue(argv, "--model"),
      key: argumentValue(argv, "--key"),
      agent: requestedAgent,
      agents: requestedAgent !== undefined ? [requestedAgent] : [],
      mode,
    },
  };
}
