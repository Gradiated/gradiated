import { RunPodError, type RunPodClient } from "@gradiated/gpu-hosts";

// Keeps the RunPod client between passes until RunPod rejects its key; the
// next request then reads the key again, so a rotated key needs no restart.
export const reloadingRunPod = (
  load: () => Promise<RunPodClient | undefined>,
) => {
  let client: RunPodClient | undefined;

  const forgettingOnRejection =
    <A extends unknown[], R>(call: (...args: A) => Promise<R>) =>
    async (...args: A) => {
      try {
        return await call(...args);
      } catch (error) {
        if (
          error instanceof RunPodError &&
          (error.status === 401 || error.status === 403)
        )
          client = undefined;
        throw error;
      }
    };

  return async () => {
    if (client) return client;

    const loaded = await load();
    if (!loaded) return undefined;

    client = {
      pod: forgettingOnRejection(loaded.pod),
      identity: forgettingOnRejection(loaded.identity),
      update: forgettingOnRejection(loaded.update),
      start: forgettingOnRejection(loaded.start),
    };
    return client;
  };
};
