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

  const database = (): Database | undefined => {
    const url = readUrl();
    if (!url) return undefined;

    if (current?.url !== url) {
      void current?.connection.close().catch(() => undefined);
      current = { url, connection: connect(url) };
    }
    return current.connection.database;
  };

  const resolve = (): SyncFleet | undefined => {
    const value = database();
    return value === undefined ? undefined : sync(value);
  };

  const close = async () => {
    await current?.connection.close().catch(() => undefined);
  };

  return { resolve, database, close };
};
