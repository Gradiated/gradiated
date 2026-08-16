import { drizzle, type NodePgDatabase } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

import { schema } from "./schema/index.js";

export type ControlDatabase = NodePgDatabase<typeof schema>;

export interface ControlDatabaseClient {
  database: ControlDatabase;
  pool: Pool;
}

export function createControlDatabase(
  connectionString: string,
): ControlDatabaseClient {
  const pool = new Pool({ connectionString });
  return {
    database: drizzle({ client: pool, schema }),
    pool,
  };
}
