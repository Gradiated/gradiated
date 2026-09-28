import { X509Certificate } from "node:crypto";
import { mkdtempSync, readFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

import {
  needsRenewal,
  renewFilesIfDue,
  renewingCertificate,
} from "../src/renewal.js";
import { cliProfile, issueCertificate } from "../src/certificates.js";
import { localSigner, testCa } from "../src/testing.js";

const issuedAt = new Date("2026-09-28T00:00:00Z");
const day = (days: number) =>
  new Date(issuedAt.getTime() + days * 24 * 60 * 60 * 1000);
const renewal = {
  caCertificate: testCa.certificate,
  signer: localSigner,
  profile: cliProfile,
};

describe("when a certificate is due", () => {
  it.each([
    [0, false],
    [19, false],
    [20, true],
    [31, true],
  ])("a 30-day certificate %i days in needs renewal: %s", async (days, due) => {
    const { certificate } = await issueCertificate(
      testCa.certificate,
      localSigner,
      cliProfile,
      issuedAt,
    );

    expect(needsRenewal(certificate, day(days))).toBe(due);
  });

  it("renews when there is no certificate yet", () => {
    expect(needsRenewal(undefined)).toBe(true);
  });
});

describe("a certificate renewed in memory", () => {
  const issuer = () =>
    vi.fn(() => issueCertificate(testCa.certificate, localSigner, cliProfile));

  it("issues once and reuses the certificate while it is fresh", async () => {
    const issue = issuer();
    const certificate = renewingCertificate(issue);

    const [first, second] = await Promise.all([
      certificate.get(),
      certificate.get(),
    ]);

    expect(await certificate.get()).toBe(first);
    expect(second).toBe(first);
    expect(issue).toHaveBeenCalledOnce();
    expect(certificate.expiry()).toBe(
      Date.parse(new X509Certificate(first.certificate).validTo) / 1000,
    );
  });

  it("reissues once the certificate is due", async () => {
    const issue = issuer();
    const certificate = renewingCertificate(issue);
    const first = await certificate.get();

    vi.useFakeTimers({ now: day(25), toFake: ["Date"] });
    const second = await certificate.get();
    vi.useRealTimers();

    expect(second).not.toBe(first);
    expect(issue).toHaveBeenCalledTimes(2);
  });

  it("reports no expiry before the first issue", () => {
    expect(renewingCertificate(issuer()).expiry()).toBeUndefined();
  });
});

describe("certificate files renewed in place", () => {
  const directory = () => mkdtempSync(path.join(tmpdir(), "nomad-tls-"));
  const read = (dir: string, name: string) =>
    readFileSync(path.join(dir, name), "utf8");

  it("writes a private key and a certificate the CA verifies", async () => {
    const dir = directory();

    await expect(renewFilesIfDue(dir, renewal, issuedAt)).resolves.toBe(true);

    const certificate = new X509Certificate(read(dir, "cert.pem"));
    expect(
      certificate.verify(new X509Certificate(testCa.certificate).publicKey),
    ).toBe(true);
    expect(read(dir, "key.pem")).toContain("PRIVATE KEY");
    expect(statSync(path.join(dir, "key.pem")).mode & 0o777).toBe(0o600);
  });

  it("leaves a fresh certificate alone and replaces a due one", async () => {
    const dir = directory();
    await renewFilesIfDue(dir, renewal, issuedAt);
    const original = read(dir, "cert.pem");

    await expect(renewFilesIfDue(dir, renewal, day(10))).resolves.toBe(false);
    expect(read(dir, "cert.pem")).toBe(original);

    await expect(renewFilesIfDue(dir, renewal, day(21))).resolves.toBe(true);
    expect(read(dir, "cert.pem")).not.toBe(original);
  });
});
