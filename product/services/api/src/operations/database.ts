import {
  createCatalogBillingService,
  createControlDatabase,
  type CatalogBillingService,
  type ControlDatabase,
} from "@gradiated/control";

export const requiredEnv = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);

  return value;
};

export const withControlDatabase = async <Result>(
  operation: (context: {
    database: ControlDatabase;
    catalog: CatalogBillingService;
  }) => Promise<Result>,
  databaseUrl = requiredEnv("DATABASE_URL"),
): Promise<Result> => {
  const { database, pool } = createControlDatabase(databaseUrl);

  try {
    return await operation({
      database,
      catalog: createCatalogBillingService(database),
    });
  } finally {
    await pool.end();
  }
};
