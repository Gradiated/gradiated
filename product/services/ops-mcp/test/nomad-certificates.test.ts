import "reflect-metadata";

import { createPrivateKey, X509Certificate } from "node:crypto";

import * as x509 from "@peculiar/x509";
import { describe, expect, it } from "vitest";

import {
  cliProfile,
  hostProfile,
  issueCertificate,
  kmsSigner,
  serverProfile,
  type CertificateSigner,
} from "../src/nomad-certificates.js";
import { fakeKms, localSigner, testCa } from "./support/nomad-ca.js";

const signers: [string, () => CertificateSigner][] = [
  ["a local key", () => localSigner],
  ["KMS", () => kmsSigner("alias/test-nomad-ca", fakeKms().client)],
];

const serverAuth = "1.3.6.1.5.5.7.3.1";
const clientAuth = "1.3.6.1.5.5.7.3.2";

describe.each(signers)("certificates signed with %s", (_name, signer) => {
  it.each([
    ["host", hostProfile, "client.global.nomad", [serverAuth, clientAuth]],
    ["cli", cliProfile, "cli.global.nomad", [clientAuth]],
    [
      "server",
      serverProfile(1),
      "server.global.nomad",
      [serverAuth, clientAuth],
    ],
  ] as const)(
    "issues a %s certificate the CA verifies",
    async (_role, profile, host, usages) => {
      const issued = await issueCertificate(
        testCa.certificate,
        signer(),
        profile,
      );
      const certificate = new X509Certificate(issued.certificate);

      expect(
        certificate.verify(new X509Certificate(testCa.certificate).publicKey),
      ).toBe(true);
      expect(certificate.checkHost(host)).toBe(host);
      expect(certificate.keyUsage).toEqual(usages);
      expect(certificate.ca).toBe(false);
      expect(certificate.publicKey.asymmetricKeyType).toBe("ec");
      expect(
        certificate.checkPrivateKey(createPrivateKey(issued.privateKey)),
      ).toBe(true);
    },
  );

  it("names its issuer with the CA's exact subject bytes, which Go requires", async () => {
    const issued = await issueCertificate(
      testCa.certificate,
      signer(),
      hostProfile,
    );

    expect(
      Buffer.from(
        new x509.X509Certificate(issued.certificate).issuerName.toArrayBuffer(),
      ),
    ).toEqual(
      Buffer.from(
        new x509.X509Certificate(
          testCa.certificate,
        ).subjectName.toArrayBuffer(),
      ),
    );
  });
});

describe("certificate profiles", () => {
  it("gives each server its cluster, headless and public RPC names", async () => {
    const issued = await issueCertificate(
      testCa.certificate,
      localSigner,
      serverProfile(2),
    );
    const certificate = new X509Certificate(issued.certificate);

    for (const name of [
      "nomad-2.nomad-headless.nomad.svc.cluster.local",
      "nomad-api.nomad.svc.cluster.local",
      "nomad-2.rpc.gradiated.com",
    ]) {
      expect(certificate.checkHost(name)).toBe(name);
    }
    expect(certificate.checkIP("127.0.0.1")).toBe("127.0.0.1");
    expect(certificate.checkHost("nomad-1.rpc.gradiated.com")).toBeUndefined();
  });

  it.each([
    [hostProfile, "2027-09-23T00:00:00.000Z"],
    [cliProfile, "2026-12-22T00:00:00.000Z"],
  ])("lasts the profile's days", async (profile, validTo) => {
    const issued = await issueCertificate(
      testCa.certificate,
      localSigner,
      profile,
      new Date("2026-09-23T00:00:00Z"),
    );

    expect(new Date(new X509Certificate(issued.certificate).validTo)).toEqual(
      new Date(validTo),
    );
  });

  it("never outlives the CA", async () => {
    const issued = await issueCertificate(
      testCa.certificate,
      localSigner,
      hostProfile,
      new Date("2126-08-01T00:00:00Z"),
    );

    expect(new Date(new X509Certificate(issued.certificate).validTo)).toEqual(
      new Date(new X509Certificate(testCa.certificate).validTo),
    );
  });
});

describe("KMS signer", () => {
  it("asks KMS to hash and sign the certificate with ECDSA SHA-256", async () => {
    const kms = fakeKms();

    await issueCertificate(
      testCa.certificate,
      kmsSigner("alias/test-nomad-ca", kms.client),
      hostProfile,
    );

    expect(kms.requests).toEqual([
      {
        KeyId: "alias/test-nomad-ca",
        MessageType: "RAW",
        SigningAlgorithm: "ECDSA_SHA_256",
      },
    ]);
  });
});
