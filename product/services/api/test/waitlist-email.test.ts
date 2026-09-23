import { describe, expect, it } from "vitest";

import { EmailDeliveryError } from "../src/email/resend.js";
import { createResendWaitlistWelcomeSender } from "../src/email/waitlist-welcome.js";

const captureRequests = () => {
  const requests: { url: string; init: RequestInit }[] = [];
  const fetch: typeof globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init: init ?? {} });

    return new Response(JSON.stringify({ id: "email-id" }), { status: 200 });
  };

  return { requests, fetch };
};

const configuration = {
  apiKey: "test-key",
  from: "Gradiated <hello@mail.gradiated.com>",
};

describe("waitlist welcome email", () => {
  it("sends the branded welcome through Resend with a plain-text fallback", async () => {
    const { requests, fetch } = captureRequests();

    await createResendWaitlistWelcomeSender({ ...configuration, fetch })({
      email: "founder@example.com",
    });

    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({
      url: "https://api.resend.com/emails",
      init: {
        method: "POST",
        headers: { Authorization: "Bearer test-key" },
      },
    });

    const body = JSON.parse(String(requests[0]?.init.body));

    expect(body).toMatchObject({
      from: configuration.from,
      to: ["founder@example.com"],
      subject: "You're on the Gradiated waitlist",
    });
    expect(body.text).toMatch(/^You're on the list\.\n\nThanks for joining/);
    expect(body.text).toContain("— Gradiated");
    expect(body.html).toContain("You&#39;re on the list.</h1>");
    expect(body.html).toContain(
      '<p style="margin:0 0 20px;font-family:Arial,sans-serif;font-size:16px;line-height:1.65;color:#444444;">Thanks for joining',
    );
    expect(body.html).not.toContain("<p>");
  });

  it("reports a provider failure with a bounded code only", async () => {
    const rejection = await createResendWaitlistWelcomeSender({
      ...configuration,
      fetch: async () =>
        new Response("private-provider-content", { status: 500 }),
    })({ email: "founder@example.com" }).catch((error: unknown) => error);

    expect(rejection).toBeInstanceOf(EmailDeliveryError);
    expect(rejection).toMatchObject({
      code: "500",
      message: expect.not.stringMatching(
        /test-key|founder@example\.com|private/,
      ),
    });
  });
});
