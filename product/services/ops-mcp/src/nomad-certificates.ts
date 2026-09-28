import "reflect-metadata";

import { randomBytes, webcrypto } from "node:crypto";

import { KMSClient, SignCommand } from "@aws-sdk/client-kms";
import * as x509 from "@peculiar/x509";

x509.cryptoProvider.set(webcrypto as Crypto);

const ecdsa = { name: "ECDSA", namedCurve: "P-256", hash: "SHA-256" };
const DAY_MS = 24 * 60 * 60 * 1000;
const CLOCK_SKEW_MS = 5 * 60 * 1000;

// Returns a WebCrypto ECDSA signature: r and s concatenated, not DER.
export type CertificateSigner = (data: ArrayBuffer) => Promise<ArrayBuffer>;

export type CertificateProfile = {
  readonly commonName: string;
  readonly dnsNames: readonly string[];
  readonly ipAddresses: readonly string[];
  readonly serverAuth: boolean;
  readonly days: number;
};

// Nomad rejects Ed25519 client keys, and hosts present their certificate on
// both sides of RPC, so client certificates carry server authentication too.
export const hostProfile: CertificateProfile = {
  commonName: "client.global.nomad",
  dnsNames: ["client.global.nomad", "localhost"],
  ipAddresses: ["127.0.0.1"],
  serverAuth: true,
  days: 365,
};

export const cliProfile: CertificateProfile = {
  commonName: "cli.global.nomad",
  dnsNames: ["cli.global.nomad"],
  ipAddresses: [],
  serverAuth: false,
  days: 90,
};

export const serverProfile = (ordinal: number): CertificateProfile => ({
  commonName: "server.global.nomad",
  dnsNames: [
    "server.global.nomad",
    `nomad-${ordinal}.nomad-headless.nomad.svc.cluster.local`,
    "nomad-api.nomad.svc.cluster.local",
    "localhost",
    `nomad-${ordinal}.rpc.gradiated.com`,
  ],
  ipAddresses: ["127.0.0.1"],
  serverAuth: true,
  days: 90,
});

const copyBytes = (data: BufferSource): ArrayBuffer =>
  (ArrayBuffer.isView(data)
    ? new Uint8Array(data.buffer, data.byteOffset, data.byteLength)
    : new Uint8Array(data)
  ).slice().buffer;

const signingCrypto = (sign: CertificateSigner): Crypto => {
  const subtle = new Proxy(webcrypto.subtle, {
    get: (target, property) =>
      property === "sign"
        ? (_algorithm: unknown, _key: unknown, data: BufferSource) =>
            sign(copyBytes(data))
        : Reflect.get(target, property, target).bind(target),
  });

  return {
    subtle,
    getRandomValues: webcrypto.getRandomValues.bind(webcrypto),
    randomUUID: webcrypto.randomUUID.bind(webcrypto),
  } as Crypto;
};

const caSigningKey = {
  algorithm: { name: "ECDSA", namedCurve: "P-256" },
  type: "private",
  extractable: false,
  usages: ["sign"],
} as unknown as CryptoKey;

export const issueCertificate = async (
  caCertificate: string,
  sign: CertificateSigner,
  profile: CertificateProfile,
  now = new Date(),
): Promise<{ certificate: string; privateKey: string }> => {
  const ca = new x509.X509Certificate(caCertificate);
  const keys = await webcrypto.subtle.generateKey(ecdsa, true, [
    "sign",
    "verify",
  ]);
  const serial = randomBytes(16);
  serial[0]! &= 0x7f;
  const expiry = Math.min(
    now.getTime() + profile.days * DAY_MS,
    ca.notAfter.getTime(),
  );

  const certificate = await x509.X509CertificateGenerator.create(
    {
      serialNumber: serial.toString("hex"),
      subject: `CN=${profile.commonName}`,
      // Go matches issuer to CA by exact bytes; re-encoding the name from text changes its string type.
      issuer: ca.subjectName,
      notBefore: new Date(now.getTime() - CLOCK_SKEW_MS),
      notAfter: new Date(expiry),
      signingAlgorithm: ecdsa,
      publicKey: keys.publicKey,
      signingKey: caSigningKey,
      extensions: [
        new x509.BasicConstraintsExtension(false, undefined, true),
        new x509.KeyUsagesExtension(x509.KeyUsageFlags.digitalSignature, true),
        new x509.ExtendedKeyUsageExtension(
          profile.serverAuth
            ? [
                x509.ExtendedKeyUsage.serverAuth,
                x509.ExtendedKeyUsage.clientAuth,
              ]
            : [x509.ExtendedKeyUsage.clientAuth],
        ),
        new x509.SubjectAlternativeNameExtension([
          ...profile.dnsNames.map((value) => ({ type: "dns" as const, value })),
          ...profile.ipAddresses.map((value) => ({
            type: "ip" as const,
            value,
          })),
        ]),
        await x509.SubjectKeyIdentifierExtension.create(keys.publicKey),
        await x509.AuthorityKeyIdentifierExtension.create(ca),
      ],
    },
    signingCrypto(sign),
  );
  const privateKey = await webcrypto.subtle.exportKey("pkcs8", keys.privateKey);

  return {
    certificate: certificate.toString("pem"),
    privateKey: x509.PemConverter.encode(privateKey, "PRIVATE KEY"),
  };
};

export const kmsSigner =
  (keyId: string, client = new KMSClient({})): CertificateSigner =>
  async (data) => {
    const { Signature } = await client.send(
      new SignCommand({
        KeyId: keyId,
        Message: new Uint8Array(data),
        MessageType: "RAW",
        SigningAlgorithm: "ECDSA_SHA_256",
      }),
    );
    const signature =
      Signature &&
      new x509.AsnEcSignatureFormatter().toWebSignature(
        ecdsa,
        new Uint8Array(Signature),
      );
    if (!signature) throw new Error("KMS returned no usable ECDSA signature");

    return signature;
  };
