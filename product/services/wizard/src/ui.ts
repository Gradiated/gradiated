import * as p from "@clack/prompts";

export const intro = (title: string): void => {
  p.intro(title);
};

export const outro = (message: string): void => {
  p.outro(message);
};

export const note = (message: string, title?: string): void => {
  p.note(message, title);
};

export const agentTable = (
  rows: ReadonlyArray<{
    name: string;
    found: boolean;
    note?: string | undefined;
  }>,
): void => {
  for (const row of rows) {
    const status = row.found ? "found" : "not found";
    const suffix = row.note !== undefined ? ` (${row.note})` : "";
    p.log.step(`${row.name.padEnd(9)} ${status}${suffix}`);
  }
};

export const success = (message: string): void => {
  p.log.success(message);
};

export const info = (message: string): void => {
  p.log.info(message);
};

export const warn = (message: string): void => {
  p.log.warn(message);
};

export function fail(message: string): never {
  p.log.error(message);
  p.outro("Setup did not complete.");
  process.exit(1);
}

export const selectOption = async <T extends string>(
  message: string,
  options: ReadonlyArray<{
    value: T;
    label: string;
    hint?: string | undefined;
  }>,
): Promise<T> => {
  const result = await p.select<T>({
    message,
    options: options.map((option) => ({
      value: option.value,
      label: option.label,
      ...(option.hint !== undefined ? { hint: option.hint } : {}),
    })) as p.Option<T>[],
  });
  if (p.isCancel(result)) {
    p.cancel("Setup cancelled.");
    process.exit(0);
  }
  return result;
};

export const selectMany = async <T extends string>(
  message: string,
  options: ReadonlyArray<{
    value: T;
    label: string;
    hint?: string | undefined;
  }>,
): Promise<T[]> => {
  const result = await p.multiselect<T>({
    message,
    options: options.map((option) => ({
      value: option.value,
      label: option.label,
      ...(option.hint !== undefined ? { hint: option.hint } : {}),
    })) as p.Option<T>[],
    required: false,
  });
  if (p.isCancel(result)) {
    p.cancel("Setup cancelled.");
    process.exit(0);
  }
  return result;
};

export const askText = async (
  message: string,
  validate: (value: string) => string | undefined,
): Promise<string> => {
  const result = await p.text({ message, validate });
  if (p.isCancel(result) || typeof result !== "string" || result.length === 0) {
    p.cancel("Setup cancelled.");
    process.exit(0);
  }
  return result;
};

export const askPassword = async (message: string): Promise<string> => {
  const result = await p.password({ message });
  if (p.isCancel(result) || typeof result !== "string" || result.length === 0) {
    p.cancel("Setup cancelled.");
    process.exit(0);
  }
  return result;
};

export const confirm = async (
  message: string,
  initial = true,
): Promise<boolean> => {
  const result = await p.confirm({ message, initialValue: initial });
  if (p.isCancel(result)) {
    p.cancel("Setup cancelled.");
    process.exit(0);
  }
  return result;
};

export const spinner = () => p.spinner();

export interface UiTask {
  title: string;
  /** Set false to skip the task entirely (no spinner line). */
  enabled?: boolean;
  /**
   * Run the step. Call `message` to update the loading text mid-step and
   * return a short completion line (shown after the checkmark), or nothing.
   */
  run: (
    message: (text: string) => void,
  ) => string | void | Promise<string | void>;
}

/** Run steps sequentially, each behind a clack loading spinner. */
export const runTasks = async (tasks: readonly UiTask[]): Promise<void> => {
  for (const task of tasks) {
    if (task.enabled === false) continue;
    const progress = p.spinner();
    progress.start(task.title);
    try {
      const result = await task.run((text) => progress.message(text));
      progress.stop(
        typeof result === "string" && result.length > 0 ? result : task.title,
      );
    } catch (error) {
      progress.stop(`${task.title} — failed`, 1);
      throw error;
    }
  }
};
