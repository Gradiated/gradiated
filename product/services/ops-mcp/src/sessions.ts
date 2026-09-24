import {
  closeSync,
  existsSync,
  fsyncSync,
  openSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { dirname } from "node:path";
import { z } from "zod";

const sessionSchema = z.object({
  client: z.string(),
  identity: z.object({ subject: z.string(), email: z.string() }),
  expires: z.number(),
  accessExpires: z.number(),
  accessHash: z.string(),
  refreshHash: z.string(),
  usedRefreshHashes: z.array(z.string()).max(1024),
});
export type Session = z.infer<typeof sessionSchema>;
const snapshotSchema = z.object({
  version: z.literal(1),
  keyId: z.string(),
  sessions: z.array(z.tuple([z.string(), sessionSchema])).max(1000),
});

// One writer, on a Recreate deployment with a persistent volume. Never persist
// plaintext bearer tokens. Complete the durable write before acknowledging a grant.
export const createSessions = (keyId: string, path?: string) => {
  let entries = new Map<string, Session>();
  let failed = false;
  if (path && existsSync(path)) {
    const snapshot = snapshotSchema.parse(
      JSON.parse(readFileSync(path, "utf8")),
    );
    if (snapshot.keyId === keyId) entries = new Map(snapshot.sessions);
  }
  const healthy = () => {
    if (failed) throw new Error("OAuth session storage unavailable");
  };
  const commit = (next: Map<string, Session>) => {
    healthy();
    if (path) {
      try {
        const fd = openSync(`${path}.tmp`, "w", 0o600);
        try {
          writeFileSync(
            fd,
            JSON.stringify({ version: 1, keyId, sessions: [...next] }),
          );
          fsyncSync(fd);
        } finally {
          closeSync(fd);
        }
        renameSync(`${path}.tmp`, path);
        const directory = openSync(dirname(path), "r");
        try {
          fsyncSync(directory);
        } finally {
          closeSync(directory);
        }
      } catch {
        // A failed rename/fsync may have changed disk state. Fail closed until restart.
        failed = true;
        throw new Error("OAuth session storage unavailable");
      }
    }
    entries = next;
  };
  return {
    get: (id: string) => {
      healthy();
      return entries.get(id);
    },
    put: (id: string, session: Session) => {
      if (!entries.has(id) && entries.size >= 1000)
        throw new Error("Session capacity reached");
      commit(new Map(entries).set(id, session));
    },
    remove: (id: string) => {
      const next = new Map(entries);
      if (next.delete(id)) commit(next);
    },
    prune: (now: number) => {
      healthy();
      const next = new Map(
        [...entries].filter(([, session]) => session.expires > now),
      );
      if (next.size !== entries.size) commit(next);
    },
  };
};
