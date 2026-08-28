import { describe, expect, it } from "vitest";

import {
  createMagicLinkEmailContent,
  createOtpCodeEmailContent,
  createTestMagicLinkTransport,
} from "../src/auth-email.js";

describe("magic-link email", () => {
  it("includes a branded sign-in action and a plain-text fallback", () => {
    const content = createMagicLinkEmailContent(
      "https://api.example.com/verify?token=secret&next=/docs",
    );

    expect(content.text).toBe(
      "Sign in to Gradiated\n\nUse this link to sign in:\nhttps://api.example.com/verify?token=secret&next=/docs\n\nThis link expires in 10 minutes and can be used once.\n\nIf you did not request this email, you can ignore it.",
    );
    expect(content.html).toContain('bgcolor="#f6f0e5"');
    expect(content.html).toContain('<h1 class="email-title"');
    expect(content.html).toContain(">Sign in to Gradiated</h1>");
    expect(content.html).toContain(
      'href="https://api.example.com/verify?token=secret&amp;next=/docs"',
    );
    expect(content.html).toContain(">Sign in</a>");
    expect(content.html).toContain("This link expires in 10 minutes");
    expect(content.html).not.toContain("Gradiated Ltd");
  });

  it("escapes the sign-in URL", () => {
    const content = createMagicLinkEmailContent(
      'https://api.example.com/verify?next="><script>alert(1)</script>',
    );

    expect(content.html).not.toContain("<script>");
    expect(content.html).toContain("&quot;&gt;&lt;script&gt;");
  });
});

describe("verification-code email", () => {
  it("uses the branded layout and includes the expiry", () => {
    const content = createOtpCodeEmailContent("841902");

    expect(content.text).toBe(
      "Your Gradiated verification code\n\n841902\n\nThis code expires in 10 minutes and can be used once.\n\nIf you did not request this email, you can ignore it.",
    );
    expect(content.html).toContain("Your verification code</h1>");
    expect(content.html).toContain(">841902</div>");
    expect(content.html).toContain("This code expires in 10 minutes");
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
