import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import {
  cliProfile,
  hostProfile,
  issueCertificate,
  kmsSigner,
  serverProfile,
  type CertificateProfile,
} from "./nomad-certificates.js";

const USAGE =
  "Usage: nomad:certificate <host|cli|server-0|server-1|server-2> <ca.pem> <new output directory>";

const profileFor = (role: string): CertificateProfile | undefined => {
  if (role === "host") return hostProfile;
  if (role === "cli") return cliProfile;

  const ordinal = /^server-([0-2])$/.exec(role)?.[1];

  return ordinal === undefined ? undefined : serverProfile(Number(ordinal));
};

const [role = "", caFile, outputDirectory] = process.argv.slice(2);
const profile = profileFor(role);
if (!profile || !caFile || !outputDirectory) throw new Error(USAGE);

const keyId = process.env.NOMAD_CA_KMS_KEY ?? "alias/gradiated-prod-nomad-ca";
const issued = await issueCertificate(
  readFileSync(caFile, "utf8"),
  kmsSigner(keyId),
  profile,
);

mkdirSync(outputDirectory, { mode: 0o700 });
const certificateFile = path.join(outputDirectory, `${role}.pem`);
const keyFile = path.join(outputDirectory, `${role}-key.pem`);
writeFileSync(certificateFile, issued.certificate, { mode: 0o600, flag: "wx" });
writeFileSync(keyFile, issued.privateKey, { mode: 0o600, flag: "wx" });

console.log(`Signed with ${keyId}: ${certificateFile}, ${keyFile}`);
