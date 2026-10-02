import { execFileSync, spawnSync } from "node:child_process";
import { copyFileSync, mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("Usage: mise run nomad:admin -- <Nomad CLI arguments>");
  process.exit(1);
}

const directory = mkdtempSync(path.join(os.tmpdir(), "nomad-admin-"));
const env = { ...process.env, AWS_PROFILE: process.env.AWS_PROFILE ?? "gradiated-admin" };
try {
  const tls = path.join(directory, "tls");
  const ca = path.join(root, "infra/environments/prod/us-east-1/kubernetes/nomad/ca.crt");
  execFileSync("pnpm", [
    "--dir", path.join(root, "product"), "--filter", "@gradiated/nomad-pki",
    "certificate", "--role", "cli", "--ca", ca, "--out", tls,
  ], { env, stdio: ["ignore", "pipe", "pipe"] });
  copyFileSync(ca, path.join(tls, "ca.pem"));
  const secret = JSON.parse(execFileSync("aws", [
    "secretsmanager", "get-secret-value", "--secret-id", "gradiated/prod/nomad/acl-bootstrap",
    "--query", "SecretString", "--output", "text",
  ], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
  if (typeof secret.SecretID !== "string" || !secret.SecretID) throw new Error("Missing management token");

  const result = spawnSync("docker", [
    "run", "--rm", "-i", "--network", "host", "--entrypoint", "nomad",
    "-e", "NOMAD_ADDR", "-e", "NOMAD_TOKEN", "-e", "NOMAD_TLS_SERVER_NAME",
    "-e", "NOMAD_CACERT=/tls/ca.pem", "-e", "NOMAD_CLIENT_CERT=/tls/cert.pem",
    "-e", "NOMAD_CLIENT_KEY=/tls/key.pem", "-v", `${tls}:/tls:ro`,
    "hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9",
    ...args,
  ], {
    env: {
      ...env,
      NOMAD_ADDR: env.NOMAD_ADDR ?? "https://nomad-api.internal.gradiated.com",
      NOMAD_TLS_SERVER_NAME: "server.global.nomad",
      NOMAD_TOKEN: secret.SecretID,
    },
    stdio: "inherit",
  });
  process.exitCode = result.status ?? 1;
} catch {
  console.error("Nomad setup failed. Check AWS SSO, tailnet access, Docker, and installed product dependencies.");
  process.exitCode = 1;
} finally {
  rmSync(directory, { recursive: true, force: true });
}
