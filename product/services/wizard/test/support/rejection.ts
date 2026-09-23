export const rejectionOf = async <E extends Error>(
  promise: Promise<unknown>,
  type: new (...args: never[]) => E,
): Promise<E> => {
  const error = await promise.then(
    () => {
      throw new Error("The promise resolved, but a rejection was expected.");
    },
    (reason: unknown) => reason,
  );
  if (!(error instanceof type)) throw error;

  return error;
};
