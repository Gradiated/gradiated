import type { SyncFleet } from "./fleet.js";

type Connection<Database> = { database: Database; close: () => Promise<void> };

// The credential may be missing at start and may rotate later, so it is read on
// every sync and the connection replaced when it changes.
export const credentialedSync = <Database>(
  readUrl: () => string | undefined,
  connect: (url: string) => Connection<Database>,
  sync: (database: Database) => SyncFleet,
) => {
  let current: { url: string; connection: Connection<Database> } | undefined;

  const resolve = (): SyncFleet | undefined => {
    const url = readUrl();
    if (!url) return undefined;

    if (current?.url !== url) {
      void current?.connection.close().catch(() => undefined);
      current = { url, connection: connect(url) };
    }
    return sync(current.connection.database);
  };

  const close = async () => {
    await current?.connection.close().catch(() => undefined);
  };

  return { resolve, close };
};
