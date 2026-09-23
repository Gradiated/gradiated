import { configureOpenRouterDistributionChannel } from "@gradiated/control";

import { requiredEnv, withControlDatabase } from "./catalog-operation.js";

const rawApiKey = requiredEnv("OPENROUTER_API_KEY");
if (!/^grad_[A-Za-z0-9_-]{43}$/.test(rawApiKey)) {
  throw new Error("OPENROUTER_API_KEY must be a Gradiated API key.");
}

const configured = await withControlDatabase(({ database }) =>
  configureOpenRouterDistributionChannel(database, rawApiKey),
);

console.log(
  `Configured OpenRouter distribution channel ${configured.organizationId} with workspace ${configured.workspaceId}`,
);
