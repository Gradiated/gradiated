import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { z } from "zod";
import { createBackend } from "./backend.js";
import { createHttp } from "./http.js";
import { createAuth } from "./auth.js";
import { productionRegistrations } from "./instances/production.js";
import {
  cliProfile,
  issueCertificate,
  kmsSigner,
  renewingCertificate,
} from "@gradiated/nomad-pki";

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
    CREDENTIALS_DIRECTORY: z.string().min(1),
    NOMAD_BASE_IMAGE: z
      .string()
      // RunPod applies its ECR delegation only to tagged references and rejects tag@digest.
      .regex(/^[a-z0-9.-]+\/[a-z0-9._/-]+:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/),
    NOMAD_CA_KMS_KEY: z.string().min(1),
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
const nomadCaFile = `${config.CREDENTIALS_DIRECTORY}/nomad-ca`;
const nomadCertificate = renewingCertificate(async () => {
  const issued = await issueCertificate(
    await readFile(nomadCaFile, "utf8"),
    kmsSigner(config.NOMAD_CA_KMS_KEY),
    cliProfile,
  );
  audit({ service: "ops-mcp", event: "certificate_renewed", name: "ops-mcp" });

  return issued;
});
const keepNomadCertificateFresh = () =>
  nomadCertificate.get().catch((error: unknown) =>
    audit({
      service: "ops-mcp",
      level: "error",
      event: "certificate_renewal_failed",
      name: "ops-mcp",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
void keepNomadCertificateFresh();
setInterval(keepNomadCertificateFresh, 60 * 60 * 1000).unref();
const backend = createBackend({
  prometheus: config.PROMETHEUS_URL,
  loki: config.LOKI_URL,
  lokiTenant: config.LOKI_TENANTS,
  alertmanager: config.ALERTMANAGER_URL,
  nomad: {
    url: config.NOMAD_URL,
    caFile: nomadCaFile,
    tokenFile: `${config.CREDENTIALS_DIRECTORY}/nomad-token`,
    clientCertificate: nomadCertificate.get,
  },
});
const { server, privateServer, metrics } = createHttp({
  host: config.MCP_HOST,
  authenticate: auth.authenticate,
  authRouter: auth.router,
  backend,
  nomadCertificateExpiry: nomadCertificate.expiry,
  registrations: productionRegistrations(
    {
      credentialsDirectory: config.CREDENTIALS_DIRECTORY,
      hostImage: config.NOMAD_BASE_IMAGE,
      caKeyId: config.NOMAD_CA_KMS_KEY,
    },
    backend,
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
