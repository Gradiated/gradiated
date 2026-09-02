import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const globalSetup = async () => {
  const apiPort = process.env.PLAYWRIGHT_API_PORT ?? "3001";
  const consolePort = process.env.PLAYWRIGHT_CONSOLE_PORT ?? "3000";
  await execFileAsync("pnpm", ["--filter", "@gradiated/api", "seed"], {
    cwd: new URL("../../..", import.meta.url),
    env: {
      ...process.env,
      SEED_API_URL: `http://127.0.0.1:${apiPort}`,
      SEED_CONSOLE_URL: `http://127.0.0.1:${consolePort}`,
    },
  });
};

export default globalSetup;
