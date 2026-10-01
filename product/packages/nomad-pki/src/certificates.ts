import {
  createHash,
  createPublicKey,
  generateKeyPairSync,
  randomBytes,
  X509Certificate,
} from "node:crypto";

import { KMSClient, SignCommand } from "@aws-sdk/client-kms";
import { AsnConvert, OctetString } from "@peculiar/asn1-schema";
import {
  AlgorithmIdentifier,
  AttributeTypeAndValue,
  AttributeValue,
  AuthorityKeyIdentifier,
  BasicConstraints,
  Certificate,
  ExtendedKeyUsage,
  Extension,
  Extensions,
  GeneralName,
  id_ce_authorityKeyIdentifier,
  id_ce_basicConstraints,
  id_ce_extKeyUsage,
  id_ce_keyUsage,
  id_ce_subjectAltName,
  id_ce_subjectKeyIdentifier,
  id_kp_clientAuth,
  id_kp_serverAuth,
  KeyIdentifier,
  KeyUsage,
  KeyUsageFlags,
  Name,
  RelativeDistinguishedName,
  SubjectAlternativeName,
  SubjectKeyIdentifier,
  SubjectPublicKeyInfo,
  TBSCertificate,
  Validity,
  Version,
} from "@peculiar/asn1-x509";

const ECDSA_WITH_SHA256 = "1.2.840.10045.4.3.2";
const COMMON_NAME = "2.5.4.3";
const DAY_MS = 24 * 60 * 60 * 1000;
const CLOCK_SKEW_MS = 5 * 60 * 1000;

// Signs with the CA key and returns a DER ECDSA-Sig-Value, as KMS does.
export type CertificateSigner = (message: Uint8Array) => Promise<Uint8Array>;

export type CertificateProfile = {
  readonly commonName: string;
  readonly dnsNames: readonly string[];
  readonly ipAddresses: readonly string[];
  readonly extendedKeyUsages: readonly string[];
  readonly days: number;
};

// Hosts present their certificate on both sides of RPC.
export const hostProfile: CertificateProfile = {
  commonName: "client.global.nomad",
  dnsNames: ["client.global.nomad", "localhost"],
  ipAddresses: ["127.0.0.1"],
  extendedKeyUsages: [id_kp_serverAuth, id_kp_clientAuth],
  days: 365,
};

export const renewableHostProfile: CertificateProfile = {
  ...hostProfile,
  days: 30,
};

export const cliProfile: CertificateProfile = {
  commonName: "cli.global.nomad",
  dnsNames: ["cli.global.nomad"],
  ipAddresses: [],
  extendedKeyUsages: [id_kp_clientAuth],
  days: 30,
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
  extendedKeyUsages: [id_kp_serverAuth, id_kp_clientAuth],
  days: 30,
});

// A DER integer is positive and minimal only if its first byte is 0x01-0x7f.
export const serialNumber = (random: Uint8Array) => {
  const serial = new Uint8Array(random);
  serial[0] = (serial[0]! & 0x7f) | 0x01;

  return serial;
};

const extension = (extnID: string, critical: boolean, value: object) =>
  new Extension({
    extnID,
    critical,
    extnValue: new OctetString(AsnConvert.serialize(value)),
  });

const keyIdentifier = ({ subjectPublicKey }: SubjectPublicKeyInfo) =>
  createHash("sha1").update(new Uint8Array(subjectPublicKey)).digest();

const commonName = (value: string) =>
  new Name([
    new RelativeDistinguishedName([
      new AttributeTypeAndValue({
        type: COMMON_NAME,
        value: new AttributeValue({ utf8String: value }),
      }),
    ]),
  ]);

export const issueCertificate = async (
  caCertificate: string,
  sign: CertificateSigner,
  profile: CertificateProfile,
  now = new Date(),
): Promise<{ certificate: string; privateKey: string }> => {
  const keys = generateKeyPairSync("ec", { namedCurve: "P-256" });
  const certificate = await issueCertificateForPublicKey(
    caCertificate,
    sign,
    profile,
    keys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    now,
  );

  return {
    certificate,
    privateKey: keys.privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString(),
  };
};

export const issueCertificateForPublicKey = async (
  caCertificate: string,
  sign: CertificateSigner,
  profile: CertificateProfile,
  publicKey: string,
  now = new Date(),
): Promise<string> => {
  const ca = AsnConvert.parse(
    new X509Certificate(caCertificate).raw,
    Certificate,
  ).tbsCertificate;
  const key = createPublicKey(publicKey);
  if (
    key.asymmetricKeyType !== "ec" ||
    key.asymmetricKeyDetails?.namedCurve !== "prime256v1"
  ) {
    throw new Error("Nomad host public keys must use P-256");
  }

  const publicKeyInfo = AsnConvert.parse(
    key.export({ type: "spki", format: "der" }),
    SubjectPublicKeyInfo,
  );
  const caExpiry = ca.validity.notAfter.getTime().getTime();
  const algorithm = new AlgorithmIdentifier({ algorithm: ECDSA_WITH_SHA256 });

  const tbsCertificate = new TBSCertificate({
    version: Version.v3,
    serialNumber: serialNumber(randomBytes(16)).buffer,
    signature: algorithm,
    // Go matches a certificate to its issuer by these exact bytes.
    issuer: ca.subject,
    validity: new Validity({
      notBefore: new Date(now.getTime() - CLOCK_SKEW_MS),
      notAfter: new Date(
        Math.min(now.getTime() + profile.days * DAY_MS, caExpiry),
      ),
    }),
    subject: commonName(profile.commonName),
    subjectPublicKeyInfo: publicKeyInfo,
    extensions: new Extensions([
      extension(
        id_ce_basicConstraints,
        true,
        new BasicConstraints({ cA: false }),
      ),
      extension(
        id_ce_keyUsage,
        true,
        new KeyUsage(KeyUsageFlags.digitalSignature),
      ),
      extension(
        id_ce_extKeyUsage,
        false,
        new ExtendedKeyUsage([...profile.extendedKeyUsages]),
      ),
      extension(
        id_ce_subjectAltName,
        false,
        new SubjectAlternativeName([
          ...profile.dnsNames.map((dNSName) => new GeneralName({ dNSName })),
          ...profile.ipAddresses.map(
            (iPAddress) => new GeneralName({ iPAddress }),
          ),
        ]),
      ),
      extension(
        id_ce_subjectKeyIdentifier,
        false,
        new SubjectKeyIdentifier(keyIdentifier(publicKeyInfo)),
      ),
      extension(
        id_ce_authorityKeyIdentifier,
        false,
        new AuthorityKeyIdentifier({
          keyIdentifier: new KeyIdentifier(
            keyIdentifier(ca.subjectPublicKeyInfo),
          ),
        }),
      ),
    ]),
  });

  const signature = await sign(
    new Uint8Array(AsnConvert.serialize(tbsCertificate)),
  );
  const certificate = new Certificate({
    tbsCertificate,
    signatureAlgorithm: algorithm,
    signatureValue: signature.slice().buffer,
  });

  return new X509Certificate(
    Buffer.from(AsnConvert.serialize(certificate)),
  ).toString();
};

export const kmsSigner =
  (
    keyId: string,
    client = new KMSClient({
      maxAttempts: 2,
      requestHandler: { connectionTimeout: 2000, requestTimeout: 5000 },
    }),
  ): CertificateSigner =>
  async (message) => {
    const { Signature } = await client.send(
      new SignCommand({
        KeyId: keyId,
        Message: message,
        MessageType: "RAW",
        SigningAlgorithm: "ECDSA_SHA_256",
      }),
    );
    if (!Signature) throw new Error("KMS returned no signature");

    return Signature;
  };
