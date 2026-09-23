export type DependencyStatus = "up" | "down";

export type DependencyProbe =
  { status: "up" } | { status: "down"; error: unknown };

export type DependencyChecks = Record<string, DependencyProbe>;

export type DependencyCheck = () => Promise<DependencyChecks>;

export class DependencyTimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`The dependency did not answer within ${timeoutMs} ms.`);
    this.name = "DependencyTimeoutError";
  }
}

const probe = async (
  check: () => Promise<unknown>,
  timeoutMs: number,
): Promise<DependencyProbe> => {
  let timer: NodeJS.Timeout | undefined;
  const timedOut = new Promise<DependencyProbe>((resolve) => {
    timer = setTimeout(
      () =>
        resolve({
          status: "down",
          error: new DependencyTimeoutError(timeoutMs),
        }),
      timeoutMs,
    );
  });
  const settled = Promise.resolve()
    .then(check)
    .then(
      (): DependencyProbe => ({ status: "up" }),
      (error: unknown): DependencyProbe => ({ status: "down", error }),
    );

  try {
    return await Promise.race([settled, timedOut]);
  } finally {
    clearTimeout(timer);
  }
};

export const createReadinessCheck =
  ({
    pool,
    valkey,
    timeoutMs,
  }: {
    pool: { query(sql: string): Promise<unknown> };
    valkey: { ping(): Promise<unknown> };
    timeoutMs: number;
  }): DependencyCheck =>
  async () => {
    const [postgres, valkeyProbe] = await Promise.all([
      probe(() => pool.query("select 1"), timeoutMs),
      probe(() => valkey.ping(), timeoutMs),
    ]);

    return { postgres, valkey: valkeyProbe };
  };
