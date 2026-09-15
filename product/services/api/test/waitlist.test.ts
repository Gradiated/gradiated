import { describe, expect, it, vi } from "vitest";

import { createApp } from "../src/app.js";
import { waitlistSignupSchema } from "@gradiated/control";

const submission = {
  email: "Founder@Example.com ",
  companySize: "11-50",
  monthlyTokenSpendUsd: "2,500",
  motivation: "Provider bills doubled two quarters running.",
};

const post = (app: ReturnType<typeof createApp>, body: unknown) =>
  app.request("/api/v1/waitlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

describe("waitlist route", () => {
  it("records a signup and sends one welcome email", async () => {
    const join = vi.fn(async (value: unknown) => ({
      created: true,
      email: waitlistSignupSchema.parse(value).email,
    }));
    const sendWaitlistWelcome = vi.fn(async () => {});
    const app = createApp({
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
    const app = createApp({
      services: {
        waitlist: {
          join: async () => ({ created: false, email: "founder@example.com" }),
        },
      },
      sendWaitlistWelcome: vi
        .fn()
        .mockRejectedValue(new Error("must not be called")),
    });

    const response = await post(app, submission);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok" });
  });

  it("keeps the form working when the email provider fails", async () => {
    const app = createApp({
      services: {
        waitlist: {
          join: async () => ({ created: true, email: "founder@example.com" }),
        },
      },
      sendWaitlistWelcome: async () => {
        throw new Error("resend is down");
      },
    });

    const response = await post(app, submission);
    expect(response.status).toBe(200);
  });

  it("rejects an invalid submission via the app's validation problem", async () => {
    const join = vi.fn();
    const app = createApp({ services: { waitlist: { join } } });

    const response = await post(app, {
      ...submission,
      companySize: "a few of us",
    });
    expect(response.status).toBe(422);
    const problem = (await response.json()) as { code?: string };
    expect(problem.code).toBe("validation_failed");
    expect(join).not.toHaveBeenCalled();
  });
});
