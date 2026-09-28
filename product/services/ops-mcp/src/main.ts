import { readFileSync } from "node:fs";
import { z } from "zod";
import { createBackend } from "./backend.js";
import { createHttp } from "./http.js";
import { createAuth } from "./auth.js";

const config = z
  .object({
    MCP_HOST: z.literal("ops.gradiated.com"),
    MCP_OIDC_SECRET_FILE: z.string().min(1),
    MCP_SESSION_FILE: z.string().min(1),
    MCP_DENIED_EMAILS: z.string().default("[]"),
    MCP_REDIRECT_URIS: z.string().default("[]"),
    PROMETHEUS_URL: z.url(),
    LOKI_URL: z.url(),
    LOKI_TENANTS: z.string().min(1),
    ALERTMANAGER_URL: z.url(),
    NOMAD_URL: z.url(),
    NOMAD_CREDENTIALS_DIRECTORY: z.string().min(1),
  })
  .parse(process.env);
const audit = (event: Record<string, unknown>) =>
  process.stdout.write(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      level: "info",
      ...event,
    }) + "\n",
  );
const auth = createAuth({
  audit,
  origin: `https://${config.MCP_HOST}`,
  clientSecret: z
    .string()
    .min(32)
    .parse(readFileSync(config.MCP_OIDC_SECRET_FILE, "utf8").trim()),
  sessionFile: config.MCP_SESSION_FILE,
  deniedEmails: z.array(z.email()).parse(JSON.parse(config.MCP_DENIED_EMAILS)),
  redirectUris: z.array(z.url()).parse(JSON.parse(config.MCP_REDIRECT_URIS)),
});
const { server, metrics } = createHttp({
  host: config.MCP_HOST,
  authenticate: auth.authenticate,
  authRouter: auth.router,
  backend: createBackend({
    prometheus: config.PROMETHEUS_URL,
    loki: config.LOKI_URL,
    lokiTenant: config.LOKI_TENANTS,
    alertmanager: config.ALERTMANAGER_URL,
    nomad: {
      url: config.NOMAD_URL,
      caFile: `${config.NOMAD_CREDENTIALS_DIRECTORY}/nomad-ca`,
      certFile: `${config.NOMAD_CREDENTIALS_DIRECTORY}/nomad-cert`,
      keyFile: `${config.NOMAD_CREDENTIALS_DIRECTORY}/nomad-key`,
      tokenFile: `${config.NOMAD_CREDENTIALS_DIRECTORY}/nomad-token`,
    },
  }),
  audit,
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
