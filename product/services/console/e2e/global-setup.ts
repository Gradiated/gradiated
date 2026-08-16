import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const globalSetup = async () => {
  await execFileAsync("pnpm", ["--filter", "@gradiated/api", "seed"], {
    cwd: new URL("../../..", import.meta.url),
    env: {
      ...process.env,
      SEED_API_URL: "http://127.0.0.1:3001",
    },
  });
};

export default globalSetup;
