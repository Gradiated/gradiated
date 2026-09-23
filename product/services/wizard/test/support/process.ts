import { spawn } from "node:child_process";
import { delimiter } from "node:path";

export interface ProcessResult {
  status: number | null;
  stdout: string;
  stderr: string;
}

export interface ProcessOptions {
  env: Readonly<Record<string, string>>;
  cwd?: string;
  pathPrepend?: readonly string[];
  shell?: boolean;
}

// Windows exposes PATH as "Path"; dropping every casing before setting PATH
// keeps a single entry in the child environment.
const inheritedEnvironment = (): Record<string, string> =>
  Object.fromEntries(
    Object.entries(process.env).filter(
      (entry): entry is [string, string] =>
        entry[0].toUpperCase() !== "PATH" && entry[1] !== undefined,
    ),
  );

export const runProcess = (
  command: string,
  args: readonly string[],
  options: ProcessOptions,
): Promise<ProcessResult> => {
  const basePath = options.env.PATH ?? process.env.PATH ?? "";
  const env = {
    ...inheritedEnvironment(),
    ...options.env,
    PATH: [...(options.pathPrepend ?? []), basePath].join(delimiter),
  };

  return new Promise((resolve, reject) => {
    const child = spawn(command, [...args], {
      env,
      cwd: options.cwd,
      shell: options.shell ?? false,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", reject);
    child.on("close", (status) => resolve({ status, stdout, stderr }));
  });
};
