import { vi } from "vitest";

export const progress = { start: vi.fn(), stop: vi.fn() };

export const intro = vi.fn();
export const outro = vi.fn();
export const note = vi.fn();
export const success = vi.fn();
export const info = vi.fn();
export const warn = vi.fn();
export const agentTable = vi.fn();
export const askText = vi.fn();
export const askPassword = vi.fn();
export const selectOption = vi.fn();
export const selectMany = vi.fn();
export const confirm = vi.fn();

export const bulletList = vi.fn((entries: readonly string[]) =>
  entries.join("\n"),
);

export const step = async <T>(
  title: string,
  run: () => Promise<T>,
  messages: { done: (result: T) => string; failed: (error: unknown) => string },
): Promise<T> => {
  progress.start(title);

  try {
    const result = await run();
    progress.stop(messages.done(result));
    return result;
  } catch (error) {
    progress.stop(messages.failed(error), 1);
    throw error;
  }
};
