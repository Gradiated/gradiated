import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { apiUrl, consoleUrl } from "./env";

const execFileAsync = promisify(execFile);

const globalSetup = async () => {
  await execFileAsync("pnpm", ["--filter", "@gradiated/api", "seed"], {
    cwd: new URL("../../..", import.meta.url),
    env: {
      ...process.env,
      SEED_API_URL: apiUrl,
      SEED_CONSOLE_URL: consoleUrl,
    },
  });
};

export default globalSetup;
