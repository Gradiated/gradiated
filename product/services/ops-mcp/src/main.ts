import { readFileSync } from "node:fs";
import { z } from "zod";
import { createBackend } from "./backend.js";
import { createHttp } from "./http.js";
import { createAuth } from "./auth.js";
import { GpuBaseImageSchema } from "./instances/image.js";
import { productionRegistrations } from "./instances/production.js";
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
    CREDENTIALS_DIRECTORY: z.string().min(1),
    GPU_BASE_IMAGE: GpuBaseImageSchema,
    GPU_HOST_BOOTSTRAP_SHA256: z
      .string()
      .regex(/^[0-9a-f]{64}$/)
      .optional(),
    GPU_HOST_BOOTSTRAP_BASE_ID: z
      .string()
      .regex(/^[A-Za-z0-9._-]{1,64}$/)
      .optional(),
    GPU_CONTROL_ENDPOINT: z.ipv4(),
    TAILSCALE_SOCKS5_PORT: z.coerce
      .number()
      .int()
      .min(1)
      .max(65535)
      .default(1055),
    TAILSCALE_LOCALAPI_SOCKET: z
      .string()
      .min(1)
      .default("/var/run/tailscale/tailscaled.sock"),
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
const backend = createBackend({
  prometheus: config.PROMETHEUS_URL,
  loki: config.LOKI_URL,
  lokiTenant: config.LOKI_TENANTS,
  alertmanager: config.ALERTMANAGER_URL,
});
const { server, privateServer, metrics } = createHttp({
  host: config.MCP_HOST,
  authenticate: auth.authenticate,
  authRouter: auth.router,
  backend,
  registrations: productionRegistrations(
    {
      credentialsDirectory: config.CREDENTIALS_DIRECTORY,
      hostImage: config.GPU_BASE_IMAGE,
      hostBundleSha256: config.GPU_HOST_BOOTSTRAP_SHA256,
      hostBundleBaseId: config.GPU_HOST_BOOTSTRAP_BASE_ID,
      apiEndpoint: config.GPU_CONTROL_ENDPOINT,
      tailnet: {
        socksPort: config.TAILSCALE_SOCKS5_PORT,
        localApiSocket: config.TAILSCALE_LOCALAPI_SOCKET,
      },
    },
    (event) => audit({ service: "ops-mcp", ...event }),
  ),
  audit,
});
server.listen(3003, "0.0.0.0");
privateServer.listen(3006, "127.0.0.1");
metrics.listen(9090, "0.0.0.0");
const shutdown = () => {
  server.close();
  privateServer.close();
  metrics.close();
  setTimeout(() => process.exit(0), 15_000).unref();
};
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
