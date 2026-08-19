import { describe, expect, it } from "vitest";

import { createTestMagicLinkTransport } from "../src/auth-email.js";

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
