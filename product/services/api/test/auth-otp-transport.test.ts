import { describe, expect, it } from "vitest";

import { createTestOtpTransport } from "../src/auth-email.js";

describe("test OTP transport", () => {
  it("normalizes the email address and consumes each code once", async () => {
    const transport = createTestOtpTransport();

    await transport.send({ email: " User@Example.com ", code: "841902" });

    expect(transport.take("user@example.com")).toBe("841902");
    expect(transport.take("user@example.com")).toBeNull();
  });

  it("keeps only the newest code for an email address", async () => {
    const transport = createTestOtpTransport();

    await transport.send({ email: "user@example.com", code: "111111" });
    await transport.send({ email: "user@example.com", code: "222222" });

    expect(transport.take("user@example.com")).toBe("222222");
  });
});
