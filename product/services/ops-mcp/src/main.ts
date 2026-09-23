import { readFileSync } from "node:fs";
import { z } from "zod";
import { createBackend } from "./backend.js";
import { createHttp } from "./http.js";
import { createAuth } from "./auth.js";

const config = z
  .object({
    MCP_HOST: z.literal("ops.gradiated.com"),
    MCP_OIDC_SECRET_FILE: z.string().min(1),
    MCP_REDIRECT_URIS: z.string().default("[]"),
    PROMETHEUS_URL: z.url(),
    LOKI_URL: z.url(),
  })
  .parse(process.env);
const auth = createAuth({
  origin: `https://${config.MCP_HOST}`,
  clientSecret: z
    .string()
    .min(32)
    .parse(readFileSync(config.MCP_OIDC_SECRET_FILE, "utf8").trim()),
  redirectUris: z.array(z.url()).parse(JSON.parse(config.MCP_REDIRECT_URIS)),
});
const { server, metrics } = createHttp({
  host: config.MCP_HOST,
  authenticate: auth.authenticate,
  authRouter: auth.router,
  backend: createBackend(
    { prometheus: config.PROMETHEUS_URL, loki: config.LOKI_URL },
    "eks-prod",
  ),
  audit: (event) =>
    process.stdout.write(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: "info",
        ...event,
      }) + "\n",
    ),
});
server.listen(3003, "0.0.0.0");
metrics.listen(9090, "0.0.0.0");
const shutdown = () => {
  server.close();
  metrics.close();
  setTimeout(() => process.exit(0), 15_000).unref();
};
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
