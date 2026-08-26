import {
  configureOpenRouterDistributionChannel,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient, type ValkeyEnvironment } from "@gradiated/valkey";

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const rawApiKey = required("OPENROUTER_API_KEY");
if (!/^grad_[A-Za-z0-9_-]{43}$/.test(rawApiKey)) {
  throw new Error("OPENROUTER_API_KEY must be a Gradiated API key.");
}

const valkeyEnvironment: ValkeyEnvironment = {
  VALKEY_URL: required("VALKEY_URL"),
};
if (
  process.env.VALKEY_IAM_CACHE_NAME &&
  process.env.VALKEY_IAM_REGION &&
  process.env.VALKEY_IAM_USER
) {
  valkeyEnvironment.VALKEY_IAM_CACHE_NAME = process.env.VALKEY_IAM_CACHE_NAME;
  valkeyEnvironment.VALKEY_IAM_REGION = process.env.VALKEY_IAM_REGION;
  valkeyEnvironment.VALKEY_IAM_USER = process.env.VALKEY_IAM_USER;
}

const { database, pool } = createControlDatabase(required("DATABASE_URL"));
const valkey = createValkeyClient(valkeyEnvironment);
await valkey.connect();

try {
  const configured = await configureOpenRouterDistributionChannel(
    database,
    createValkeyServingProjector(valkey),
    rawApiKey,
  );
  console.log(
    `Configured OpenRouter distribution channel ${configured.organizationId} with workspace ${configured.workspaceId}`,
  );
} finally {
  if (valkey.isOpen) await valkey.quit();
  await pool.end();
}
