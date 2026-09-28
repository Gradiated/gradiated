import { readdir, readFile } from "node:fs/promises";
import { createServer } from "node:http";
import path from "node:path";

import { Gauge, Registry } from "prom-client";
import { z } from "zod";

import { expiryTimestamp, renewFilesIfDue } from "./certificate-renewal.js";
import { cliProfile, kmsSigner, serverProfile } from "./nomad-certificates.js";

const CHECK_INTERVAL_MS = 15 * 60 * 1000;
const RETRY_INTERVAL_MS = 60 * 1000;

const config = z
  .object({
    RENEWER_ROLE: z.enum(["server", "cli"]),
    CERTIFICATE_NAME: z.string().min(1).optional(),
    POD_NAME: z.string().optional(),
    NOMAD_CA_FILE: z.string().min(1),
    NOMAD_CA_KMS_KEY: z.string().min(1),
    TLS_DIRECTORY: z.string().min(1),
    RELOAD_COMMAND: z.string().min(1),
    METRICS_PORT: z.coerce.number().int().default(9102),
  })
  .parse(process.env);

const ordinal = /-(\d+)$/.exec(config.POD_NAME ?? "")?.[1];
if (config.RENEWER_ROLE === "server" && ordinal === undefined) {
  throw new Error("A server renewer needs POD_NAME ending in its ordinal");
}

const profile =
  config.RENEWER_ROLE === "server"
    ? serverProfile(Number(ordinal))
    : cliProfile;
const name =
  config.CERTIFICATE_NAME ??
  (config.RENEWER_ROLE === "server" ? `server-${ordinal}` : "cli");
const certificateFile = path.join(config.TLS_DIRECTORY, "cert.pem");

const renewal = {
  caCertificate: await readFile(config.NOMAD_CA_FILE, "utf8"),
  signer: kmsSigner(config.NOMAD_CA_KMS_KEY),
  profile,
};

// Signal the process whose command line starts with RELOAD_COMMAND, found
// through the pod's shared process namespace.
const reload = async () => {
  for (const pid of await readdir("/proc")) {
    if (!/^\d+$/.test(pid)) continue;

    const commandLine = await readFile(`/proc/${pid}/cmdline`, "utf8")
      .then((raw) => raw.replaceAll("\0", " ").trim())
      .catch(() => "");
    if (commandLine.startsWith(config.RELOAD_COMMAND)) {
      process.kill(Number(pid), "SIGHUP");
      console.log(JSON.stringify({ event: "certificate_reloaded", name, pid }));
    }
  }
};

const registry = new Registry();
new Gauge({
  name: "nomad_certificate_expiry_timestamp_seconds",
  help: "Expiry of a Nomad certificate that renews itself",
  labelNames: ["certificate"],
  registers: [registry],
  async collect() {
    try {
      this.set(
        { certificate: name },
        expiryTimestamp(await readFile(certificateFile, "utf8")),
      );
    } catch {
      this.reset();
    }
  },
});
createServer(async (request, response) => {
  if (request.url !== "/metrics") {
    response.writeHead(404).end();
    return;
  }

  response.setHeader("content-type", registry.contentType);
  response.end(await registry.metrics());
}).listen(config.METRICS_PORT, "0.0.0.0");

for (;;) {
  let wait = CHECK_INTERVAL_MS;

  try {
    if (await renewFilesIfDue(config.TLS_DIRECTORY, renewal)) {
      console.log(JSON.stringify({ event: "certificate_renewed", name }));
      await reload();
    }
  } catch (error) {
    wait = RETRY_INTERVAL_MS;
    console.error(
      JSON.stringify({
        event: "certificate_renewal_failed",
        name,
        error: error instanceof Error ? error.message : String(error),
      }),
    );
  }

  await new Promise((resolve) => setTimeout(resolve, wait));
}
