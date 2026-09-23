export const sleep = async (
  milliseconds: number,
  signal: AbortSignal,
): Promise<void> => {
  if (signal.aborted) return;

  await new Promise<void>((resolve) => {
    const finish = () => {
      clearTimeout(timeout);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const timeout = setTimeout(finish, milliseconds);

    signal.addEventListener("abort", finish, { once: true });
  });
};
