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
    expect(content.html).toContain('bgcolor="#f6f3ec"');
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

describe("Resend transport", () => {
  it("sends both email types with HTML and plain text", async () => {
    const { createResendMagicLinkSender, createResendOtpSender } =
      await import("../src/auth-email.js");
    const requests: { url: string; init: RequestInit }[] = [];
    const fetcher: typeof fetch = async (url, init) => {
      requests.push({ url: String(url), init: init! });
      return new Response(JSON.stringify({ id: "email-id" }), { status: 200 });
    };
    const config = {
      apiKey: "test-key",
      from: "Gradiated <auth@mail.gradiated.com>",
      fetch: fetcher,
    };
    await createResendMagicLinkSender(config)({
      email: "user@example.com",
      url: "https://example.com/verify",
    });
    await createResendOtpSender(config)({
      email: "user@example.com",
      code: "123456",
    });
    expect(requests).toHaveLength(2);
    for (const request of requests) {
      expect(request.url).toBe("https://api.resend.com/emails");
      expect(request.init.method).toBe("POST");
      expect(request.init.headers).toMatchObject({
        Authorization: "Bearer test-key",
      });
      const body = JSON.parse(String(request.init.body));
      expect(body.from).toBe(config.from);
      expect(body.to).toEqual(["user@example.com"]);
      expect(body.html).toContain("Gradiated");
      expect(body.text).toContain("10 minutes");
    }
    expect(JSON.parse(String(requests[0]!.init.body)).text).toContain(
      "https://example.com/verify",
    );
    expect(JSON.parse(String(requests[1]!.init.body)).text).toContain("123456");
  });

  it("rejects provider and network failures without exposing their content", async () => {
    const { createResendOtpSender } = await import("../src/auth-email.js");
    const config = { apiKey: "test-key", from: "auth@mail.gradiated.com" };
    const failed: typeof fetch = async () =>
      new Response("private-provider-content", { status: 403 });
    await expect(
      createResendOtpSender({ ...config, fetch: failed })({
        email: "user@example.com",
        code: "123456",
      }),
    ).rejects.toThrow("Email delivery failed (Resend HTTP 403).");
    const network: typeof fetch = async () => {
      throw new Error("private-network-content");
    };
    await expect(
      createResendOtpSender({ ...config, fetch: network })({
        email: "user@example.com",
        code: "123456",
      }),
    ).rejects.toThrow("Email delivery request failed.");
  });
});
