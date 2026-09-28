import { X509Certificate } from "node:crypto";
import { readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  issueCertificate,
  type CertificateProfile,
  type CertificateSigner,
} from "./certificates.js";

export type IssuedCertificate = { certificate: string; privateKey: string };

// Renew once two thirds of the lifetime has passed, leaving a third to notice a broken renewer.
export const needsRenewal = (
  certificate: string | undefined,
  now = new Date(),
) => {
  if (!certificate) return true;

  const { validFrom, validTo } = new X509Certificate(certificate);
  const issued = Date.parse(validFrom);
  const expires = Date.parse(validTo);

  return now.getTime() >= expires - (expires - issued) / 3;
};

export const expiryTimestamp = (certificate: string) =>
  Date.parse(new X509Certificate(certificate).validTo) / 1000;

export type Renewal = {
  readonly caCertificate: string;
  readonly signer: CertificateSigner;
  readonly profile: CertificateProfile;
};

// Keeps a certificate in memory and reissues it on use once it is due.
export const renewingCertificate = (
  issue: () => Promise<IssuedCertificate>,
) => {
  let current: IssuedCertificate | undefined;
  let pending: Promise<IssuedCertificate> | undefined;

  const renew = () =>
    (pending ??= issue()
      .then((issued) => (current = issued))
      .finally(() => (pending = undefined)));

  return {
    get: async () =>
      current && !needsRenewal(current.certificate) ? current : renew(),
    expiry: () => current && expiryTimestamp(current.certificate),
  };
};

const readOptional = async (file: string) => {
  try {
    return await readFile(file, "utf8");
  } catch {
    return undefined;
  }
};

const writeAtomically = async (file: string, contents: string) => {
  await writeFile(`${file}.new`, contents, { mode: 0o600 });
  await rename(`${file}.new`, file);
};

export const renewFilesIfDue = async (
  directory: string,
  renewal: Renewal,
  now = new Date(),
) => {
  const certificateFile = path.join(directory, "cert.pem");
  if (!needsRenewal(await readOptional(certificateFile), now)) return false;

  const issued = await issueCertificate(
    renewal.caCertificate,
    renewal.signer,
    renewal.profile,
    now,
  );
  await writeAtomically(path.join(directory, "key.pem"), issued.privateKey);
  await writeAtomically(certificateFile, issued.certificate);

  return true;
};
