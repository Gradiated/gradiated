/** Thrown by a check that can never succeed, so polling stops rather than waits out. */
export class Fatal extends Error {}

export const eventually = async <T>(
  check: () => T | Promise<T>,
  timeoutMs = 5000,
  description = "condition did not become true before deadline",
): Promise<NonNullable<T>> => {
  const deadline = Date.now() + timeoutMs;
  let last: unknown;

  while (Date.now() < deadline) {
    try {
      const result = await check();
      if (result) return result;
    } catch (error) {
      if (error instanceof Fatal) throw error;
      last = error;
    }

    await new Promise((resolve) => setTimeout(resolve, 20));
  }

  throw new Error(last ? `${description}: ${String(last)}` : description);
};

export type Outcome<T> =
  { readonly settled: true; readonly value: T } | { readonly settled: false };

export const within = async <T>(
  promise: Promise<T>,
  timeoutMs: number,
): Promise<Outcome<T>> => {
  let timer: NodeJS.Timeout | undefined;
  const expiry = new Promise<Outcome<T>>((resolve) => {
    timer = setTimeout(() => resolve({ settled: false }), timeoutMs);
  });

  try {
    return await Promise.race([
      promise.then((value): Outcome<T> => ({ settled: true, value })),
      expiry,
    ]);
  } finally {
    clearTimeout(timer);
  }
};

export interface Deferred<T = void> {
  readonly promise: Promise<T>;
  readonly resolve: (value: T) => void;
  readonly settled: () => boolean;
}

export const deferred = <T = void>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  let done = false;
  const promise = new Promise<T>((settle) => {
    resolve = (value) => {
      done = true;
      settle(value);
    };
  });

  return { promise, resolve, settled: () => done };
};
