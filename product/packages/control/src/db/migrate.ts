import { migrate } from "drizzle-orm/node-postgres/migrator";

import { createControlDatabase } from "./client.js";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) throw new Error("DATABASE_URL is required");

// A migration waiting behind a long transaction queues every reader of its
// table behind it; failing fast lets the job retry instead.
const { database, pool } = createControlDatabase(
  connectionString,
  10,
  "-c lock_timeout=5s",
);

try {
  const deadline = Date.now() + 60_000;

  for (;;) {
    try {
      await pool.query("select 1");
      break;
    } catch (error) {
      if (Date.now() >= deadline) throw error;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }

  await migrate(database, {
    migrationsFolder: new URL("../../migrations", import.meta.url).pathname,
  });
} finally {
  await pool.end();
}
