import { describe, expect, it } from "vitest";

import {
  createMagicLinkEmailContent,
  createTestMagicLinkTransport,
} from "../src/auth-email.js";

describe("magic-link email", () => {
  it("starts with one sign-in link and does not repeat the instruction", () => {
    const content = createMagicLinkEmailContent(
      "https://api.example.com/verify?token=secret&next=/docs",
    );

    expect(content.text).toBe(
      "https://api.example.com/verify?token=secret&next=/docs\n\nThis link expires in 10 minutes and can be used once.\n\nIf you did not request it, you can ignore this email.",
    );
    expect(content.html).toBe(
      '<!doctype html><html><body><p><a href="https://api.example.com/verify?token=secret&amp;next=/docs">Sign in to Gradiated</a></p><p>This link expires in 10 minutes and can be used once.</p><p>If you did not request it, you can ignore this email.</p></body></html>',
    );
    expect(content.html).not.toContain("<p>Sign in to Gradiated.</p>");
  });
});

describe("test magic-link transport", () => {
  it("normalizes the email address and consumes each link once", async () => {
    const transport = createTestMagicLinkTransport();

    await transport.send({
      email: " User@Example.com ",
      url: "https://api.example.com/verify?token=secret",
    });

    expect(transport.take("user@example.com")).toBe(
      "https://api.example.com/verify?token=secret",
    );
    expect(transport.take("user@example.com")).toBeNull();
  });

  it("keeps only the newest link for an email address", async () => {
    const transport = createTestMagicLinkTransport();

    await transport.send({ email: "user@example.com", url: "first" });
    await transport.send({ email: "user@example.com", url: "second" });

    expect(transport.take("user@example.com")).toBe("second");
  });
});
