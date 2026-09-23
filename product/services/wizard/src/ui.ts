import * as p from "@clack/prompts";

export const intro = (title: string): void => {
  p.intro(title);
};

export const outro = (message: string): void => {
  p.outro(message);
};

export const note = (message: string, title: string): void => {
  p.note(message, title);
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

export const fail: (message: string) => never = (message) => {
  p.log.error(message);
  p.outro("The wizard did not finish.");
  process.exit(1);
};

export const agentTable = (
  rows: ReadonlyArray<{ name: string; found: boolean }>,
): void => {
  for (const row of rows) {
    p.log.step(`${row.name.padEnd(9)} ${row.found ? "found" : "not found"}`);
  }
};

export const bulletList = (entries: readonly string[]): string =>
  entries.map((entry) => `  - ${entry}`).join("\n");

const cancel = (): never => {
  p.cancel("Cancelled.");
  process.exit(0);
};

const exitIfCancelled = <T>(result: T | symbol): T =>
  p.isCancel(result) ? cancel() : result;

// Clack types an empty submission as a string, but it resolves to undefined.
const exitIfEmpty = (result: string | symbol): string => {
  const text = exitIfCancelled(result);

  return typeof text === "string" && text.length > 0 ? text : cancel();
};

export const selectOption = async <T>(
  message: string,
  options: p.Option<T>[],
): Promise<T> => exitIfCancelled(await p.select({ message, options }));

export const selectMany = async <T>(
  message: string,
  options: p.Option<T>[],
): Promise<T[]> =>
  exitIfCancelled(await p.multiselect({ message, options, required: false }));

export const askText = async (
  message: string,
  validate: (value: string) => string | undefined,
): Promise<string> =>
  exitIfEmpty(
    await p.text({ message, validate: (value) => validate(value ?? "") }),
  );

export const askPassword = async (message: string): Promise<string> =>
  exitIfEmpty(await p.password({ message }));

export const confirm = async (message: string): Promise<boolean> =>
  exitIfCancelled(await p.confirm({ message }));

export const step = async <T>(
  title: string,
  run: () => Promise<T>,
  messages: { done: (result: T) => string; failed: (error: unknown) => string },
): Promise<T> => {
  const progress = p.spinner();
  progress.start(title);

  let result: T;
  try {
    result = await run();
  } catch (error) {
    progress.stop(messages.failed(error), 1);
    throw error;
  }

  progress.stop(messages.done(result));
  return result;
};
