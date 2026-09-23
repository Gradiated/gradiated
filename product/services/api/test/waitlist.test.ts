import { waitlistSignupSchema } from "@gradiated/control";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EmailDeliveryError } from "../src/email/resend.js";
import { createLoggingWaitlistWelcomeSender } from "../src/email/waitlist-welcome.js";
import {
  captureServiceLogs,
  createTestApp,
  expectProblem,
  postJson,
  validationProblem,
  type TestApp,
} from "./support.js";

const submission = {
  email: "Founder@Example.com ",
  companySize: "11-50",
  monthlyTokenSpendUsd: "2,500",
  motivation: "Provider bills doubled two quarters running.",
};

const post = (app: TestApp, body: unknown) =>
  postJson(app, "/api/v1/waitlist", body);

afterEach(() => {
  vi.restoreAllMocks();
});

describe("waitlist route", () => {
  it("records a signup and sends one welcome email", async () => {
    const join = vi.fn(async (value: unknown) => ({
      created: true,
      email: waitlistSignupSchema.parse(value).email,
    }));
    const sendWaitlistWelcome = vi.fn(async () => {});
    const app = createTestApp({
      services: { waitlist: { join } },
      sendWaitlistWelcome,
    });

    const response = await post(app, submission);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok" });

    expect(join).toHaveBeenCalledOnce();
    await vi.waitFor(() =>
      expect(sendWaitlistWelcome).toHaveBeenCalledWith({
        email: "founder@example.com",
      }),
    );
  });

  it("answers a repeat signup identically, without a second email", async () => {
    const sendWaitlistWelcome = vi.fn(async () => {});
    const app = createTestApp({
      services: {
        waitlist: {
          join: async () => ({ created: false, email: "founder@example.com" }),
        },
      },
      sendWaitlistWelcome,
    });

    const response = await post(app, submission);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok" });
    expect(sendWaitlistWelcome).not.toHaveBeenCalled();
  });

  it("keeps the form working and logs the code when the email provider fails", async () => {
    const logs = captureServiceLogs();
    const app = createTestApp({
      services: {
        waitlist: {
          join: async () => ({ created: true, email: "founder@example.com" }),
        },
      },
      sendWaitlistWelcome: async () => {
        throw new EmailDeliveryError("503", "Email delivery failed.");
      },
    });

    const response = await post(app, submission);

    expect(response.status).toBe(200);
    await vi.waitFor(() => expect(logs.lines()).toHaveLength(1));
    expect(logs.events()).toEqual([
      expect.objectContaining({
        event: "welcome_email_failed",
        error_code: "503",
      }),
    ]);
    expect(logs.lines().join("\n")).not.toContain("founder@example.com");
  });

  it("logs a skipped welcome email without the address", async () => {
    const logs = captureServiceLogs();

    await createLoggingWaitlistWelcomeSender()({
      email: "founder@example.com",
    });

    expect(logs.events()).toEqual([
      expect.objectContaining({
        level: "info",
        event: "waitlist_welcome_skipped",
      }),
    ]);
    expect(logs.lines().join("\n")).not.toContain("founder@example.com");
  });

  it("rejects an invalid submission via the app's validation problem", async () => {
    const join = vi.fn();
    const app = createTestApp({ services: { waitlist: { join } } });

    const response = await post(app, {
      ...submission,
      companySize: "a few of us",
    });
    await expectProblem(response, validationProblem);
    expect(join).not.toHaveBeenCalled();
  });
});
