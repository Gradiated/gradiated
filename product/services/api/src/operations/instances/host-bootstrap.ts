import "reflect-metadata";

import {
  createPrivateKey,
  randomBytes,
  randomUUID,
  webcrypto,
} from "node:crypto";

import * as x509 from "@peculiar/x509";

x509.cryptoProvider.set(webcrypto as Crypto);

const ecdsa = { name: "ECDSA", namedCurve: "P-256", hash: "SHA-256" };
const CLIENT_NAME = "client.global.nomad";
const CERTIFICATE_DAYS = 365;
const DAY_MS = 24 * 60 * 60 * 1000;
const CLOCK_SKEW_MS = 5 * 60 * 1000;

export interface NomadCertificateAuthority {
  readonly certificate: string;
  readonly privateKey: string;
}

export interface ArtifactCredentials {
  readonly accessKeyId: string;
  readonly secretAccessKey: string;
}

export interface HostBootstrap {
  readonly instanceId: string;
  readonly nodeName: string;
  readonly nomadNodeId: string;
  readonly nomadNodeSecret: string;
  readonly ca: string;
  readonly certificate: string;
  readonly privateKey: string;
  readonly artifact: ArtifactCredentials;
}

export const nodeName = (provider: string, providerInstanceId: string) => {
  const name = `${provider}-${providerInstanceId}`.toLowerCase();
  if (!/^[a-z0-9-]{1,63}$/.test(name)) {
    throw new Error(`${name} is not a valid Nomad node name`);
  }

  return name;
};

// Nomad rejects Ed25519 client keys.
export const issueNomadClientCertificate = async (
  authority: NomadCertificateAuthority,
  now = new Date(),
): Promise<{ certificate: string; privateKey: string }> => {
  const caCertificate = new x509.X509Certificate(authority.certificate);
  const signingKey = await webcrypto.subtle.importKey(
    "pkcs8",
    createPrivateKey(authority.privateKey).export({
      type: "pkcs8",
      format: "der",
    }),
    ecdsa,
    false,
    ["sign"],
  );
  const keys = await webcrypto.subtle.generateKey(ecdsa, true, [
    "sign",
    "verify",
  ]);
  const serial = randomBytes(16);
  serial[0]! &= 0x7f;
  const expiry = Math.min(
    now.getTime() + CERTIFICATE_DAYS * DAY_MS,
    caCertificate.notAfter.getTime(),
  );

  const certificate = await x509.X509CertificateGenerator.create({
    serialNumber: serial.toString("hex"),
    subject: `CN=${CLIENT_NAME}`,
    // Go matches issuer to CA by exact bytes; re-encoding the name from text changes its string type.
    issuer: caCertificate.subjectName,
    notBefore: new Date(now.getTime() - CLOCK_SKEW_MS),
    notAfter: new Date(expiry),
    signingAlgorithm: ecdsa,
    publicKey: keys.publicKey,
    signingKey,
    extensions: [
      new x509.BasicConstraintsExtension(false, undefined, true),
      new x509.KeyUsagesExtension(x509.KeyUsageFlags.digitalSignature, true),
      new x509.ExtendedKeyUsageExtension([
        x509.ExtendedKeyUsage.serverAuth,
        x509.ExtendedKeyUsage.clientAuth,
      ]),
      new x509.SubjectAlternativeNameExtension([
        { type: "dns", value: CLIENT_NAME },
        { type: "dns", value: "localhost" },
        { type: "ip", value: "127.0.0.1" },
      ]),
      await x509.SubjectKeyIdentifierExtension.create(keys.publicKey),
      await x509.AuthorityKeyIdentifierExtension.create(caCertificate),
    ],
  });
  const privateKey = await webcrypto.subtle.exportKey("pkcs8", keys.privateKey);

  return {
    certificate: certificate.toString("pem"),
    privateKey: x509.PemConverter.encode(privateKey, "PRIVATE KEY"),
  };
};

// Nomad refuses a known node id presented with a different secret, so a returning
// node reuses both from the bootstrap the machine already carries.
export const nomadNodeIdentity = (
  boundNodeId: string | null,
  environment: Readonly<Record<string, string>>,
) => {
  const secret = environment.GRADIATED_NOMAD_NODE_SECRET;
  if (
    boundNodeId &&
    environment.GRADIATED_NOMAD_NODE_ID === boundNodeId &&
    secret
  ) {
    return { nomadNodeId: boundNodeId, nomadNodeSecret: secret };
  }

  return { nomadNodeId: randomUUID(), nomadNodeSecret: randomUUID() };
};

const base64 = (value: string) => Buffer.from(value).toString("base64");

export const hostBootstrapEnvironment = (
  host: HostBootstrap,
): Record<string, string> => {
  const { accessKeyId, secretAccessKey } = host.artifact;
  // The host sources this file, so accept only what AWS issues.
  if (!/^[A-Z0-9]{16,128}$/.test(accessKeyId)) {
    throw new Error("Artifact access key id has an unexpected format");
  }
  if (!/^[A-Za-z0-9/+]{40}$/.test(secretAccessKey)) {
    throw new Error("Artifact secret access key has an unexpected format");
  }

  return {
    GRADIATED_INSTANCE_ID: host.instanceId,
    GRADIATED_NODE_NAME: host.nodeName,
    GRADIATED_NOMAD_NODE_ID: host.nomadNodeId,
    GRADIATED_NOMAD_NODE_SECRET: host.nomadNodeSecret,
    GRADIATED_NOMAD_CA: base64(host.ca),
    GRADIATED_NOMAD_CERT: base64(host.certificate),
    GRADIATED_NOMAD_KEY: base64(host.privateKey),
    GRADIATED_ARTIFACT_ENV: base64(
      `AWS_ACCESS_KEY_ID=${accessKeyId}\nAWS_SECRET_ACCESS_KEY=${secretAccessKey}\n`,
    ),
  };
};
