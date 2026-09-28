import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";

import {
  cliProfile,
  hostProfile,
  issueCertificate,
  kmsSigner,
  serverProfile,
  type CertificateProfile,
} from "../src/nomad-certificates.js";

const profiles: Record<string, CertificateProfile> = {
  host: hostProfile,
  cli: cliProfile,
  "server-0": serverProfile(0),
  "server-1": serverProfile(1),
  "server-2": serverProfile(2),
};

const { values } = parseArgs({
  options: {
    role: { type: "string" },
    ca: { type: "string" },
    out: { type: "string" },
    "kms-key": { type: "string", default: "alias/gradiated-prod-nomad-ca" },
  },
});
const profile = profiles[values.role ?? ""];
if (!profile || !values.ca || !values.out) {
  throw new Error(
    `Usage: nomad:certificate --role <${Object.keys(profiles).join("|")}> ` +
      "--ca <ca.pem> --out <new directory> [--kms-key <key id or alias>]",
  );
}

const issued = await issueCertificate(
  readFileSync(values.ca, "utf8"),
  kmsSigner(values["kms-key"]),
  profile,
);

mkdirSync(values.out, { mode: 0o700 });
const certificateFile = path.join(values.out, "cert.pem");
const keyFile = path.join(values.out, "key.pem");
writeFileSync(certificateFile, issued.certificate, { mode: 0o600, flag: "wx" });
writeFileSync(keyFile, issued.privateKey, { mode: 0o600, flag: "wx" });

console.log(
  `Signed ${values.role} with ${values["kms-key"]}: ${certificateFile}`,
);
