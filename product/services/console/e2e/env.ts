const apiPort = process.env.PLAYWRIGHT_API_PORT ?? "3001";
const consolePort = process.env.PLAYWRIGHT_CONSOLE_PORT ?? "3000";

export const apiUrl = `http://127.0.0.1:${apiPort}`;
export const consoleUrl = `http://127.0.0.1:${consolePort}`;
export const databaseUrl =
  process.env.DATABASE_URL ??
  "postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated";
