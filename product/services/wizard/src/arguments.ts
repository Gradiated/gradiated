import { parseArgs } from "node:util";
import type { AccountMode } from "./account.js";
import { AGENT_NAMES, type AgentName } from "./agents/names.js";
import { WizardError } from "./errors.js";

const DEFAULT_API_BASE_URL = "https://api.gradiated.com";

export type Credential =
  | { kind: "key"; key: string }
  | { kind: "account"; mode: AccountMode }
  | { kind: "discover"; environmentKey: string | null };

export interface ArgumentContext {
  stdinIsTTY: boolean;
  environmentKey: string | null;
}

export interface AgentRunOptions {
  agent: AgentName | undefined;
  dryRun: boolean;
  interactive: boolean;
}

export type UninstallOptions = AgentRunOptions;

export interface InstallOptions extends AgentRunOptions {
  credential: Credential;
  model: string | undefined;
  apiBaseUrl: string;
}

export type Command =
  | { kind: "help" }
  | { kind: "version" }
  | { kind: "install"; options: InstallOptions }
  | { kind: "uninstall"; options: UninstallOptions };

export class UsageError extends WizardError {
  constructor(problem: string) {
    super(`${problem} Run gradiated --help to see the options.`);
    this.name = "UsageError";
  }
}

const OPTIONS = {
  signup: { type: "boolean" },
  login: { type: "boolean" },
  key: { type: "string" },
  agent: { type: "string" },
  model: { type: "string" },
  "api-base-url": { type: "string" },
  "dry-run": { type: "boolean" },
  yes: { type: "boolean" },
  help: { type: "boolean" },
  version: { type: "boolean" },
} as const;

const INSTALL_ONLY_OPTIONS = [
  "signup",
  "login",
  "key",
  "model",
  "api-base-url",
] as const;

type ParsedValues = ReturnType<typeof parseTokens>["values"];

const isAgentName = (value: string): value is AgentName =>
  AGENT_NAMES.some((name) => name === value);

const parseAgent = (value: string | undefined): AgentName | undefined => {
  if (value === undefined || isAgentName(value)) return value;

  throw new UsageError(
    `Unsupported agent "${value}". Use ${AGENT_NAMES.map((name) => `"${name}"`).join(", ")}.`,
  );
};

const parseApiBaseUrl = (value: string | undefined): string => {
  if (value === undefined) return DEFAULT_API_BASE_URL;

  try {
    new URL(value);
  } catch {
    throw new UsageError(`"${value}" is not a valid --api-base-url.`);
  }

  return value.replace(/\/+$/, "");
};

const parseTokens = (argv: readonly string[]) => {
  try {
    return parseArgs({
      args: [...argv],
      options: OPTIONS,
      allowPositionals: true,
      strict: true,
    });
  } catch (error) {
    throw new UsageError(
      error instanceof Error ? error.message : String(error),
    );
  }
};

const parseCredential = (
  values: ParsedValues,
  environmentKey: string | null,
): Credential => {
  const flags = [
    values.key !== undefined && "--key",
    values.signup === true && "--signup",
    values.login === true && "--login",
  ].filter((flag) => flag !== false);
  if (flags.length > 1) {
    throw new UsageError(`${flags.join(" and ")} cannot be used together.`);
  }

  if (values.key !== undefined) return { kind: "key", key: values.key };
  if (values.signup === true) return { kind: "account", mode: "signup" };
  if (values.login === true) return { kind: "account", mode: "login" };
  return { kind: "discover", environmentKey };
};

const parseUninstall = (
  values: ParsedValues,
  options: AgentRunOptions,
): Command => {
  const unsupported = INSTALL_ONLY_OPTIONS.find(
    (name) => values[name] !== undefined,
  );
  if (unsupported !== undefined) {
    throw new UsageError(`uninstall does not accept --${unsupported}.`);
  }

  return { kind: "uninstall", options };
};

const parseInstall = (
  values: ParsedValues,
  context: ArgumentContext,
  options: AgentRunOptions,
): Command => {
  const credential = parseCredential(values, context.environmentKey);
  if (options.dryRun && credential.kind === "account") {
    throw new UsageError(
      "--dry-run cannot be used with --signup or --login, which create an account.",
    );
  }

  return {
    kind: "install",
    options: {
      ...options,
      credential,
      model: values.model,
      apiBaseUrl: parseApiBaseUrl(values["api-base-url"]),
    },
  };
};

export const parseArguments = (
  argv: readonly string[],
  context: ArgumentContext,
): Command => {
  const { values, positionals } = parseTokens(argv);

  if (positionals.length > 1) {
    throw new UsageError(`Unexpected argument "${positionals[1]}".`);
  }

  const command = positionals[0] ?? "install";
  if (command !== "install" && command !== "uninstall" && command !== "help") {
    throw new UsageError(`Unknown command "${command}".`);
  }

  if (values.help === true || command === "help") return { kind: "help" };
  if (values.version === true) return { kind: "version" };

  const options: AgentRunOptions = {
    agent: parseAgent(values.agent),
    dryRun: values["dry-run"] === true,
    interactive: values.yes !== true && context.stdinIsTTY,
  };

  return command === "uninstall"
    ? parseUninstall(values, options)
    : parseInstall(values, context, options);
};
