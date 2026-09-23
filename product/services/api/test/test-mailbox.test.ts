import { describe, expect, it } from "vitest";

import { createTestMailbox } from "../src/email/test-mailbox.js";

describe("test mailbox", () => {
  it("normalizes the email address and hands each message out once", () => {
    const mailbox = createTestMailbox();

    mailbox.send(" User@Example.com ", "841902");

    expect(mailbox.take("user@example.com")).toBe("841902");
    expect(mailbox.take("user@example.com")).toBeNull();
  });

  it("keeps only the newest message for an email address", () => {
    const mailbox = createTestMailbox();

    mailbox.send("user@example.com", "first");
    mailbox.send("user@example.com", "second");

    expect(mailbox.take("user@example.com")).toBe("second");
  });
});
