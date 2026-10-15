import { describe, expect, it } from "vitest";

import {
  createResendInvitationSender,
  invitationUrl,
} from "../src/email/invitation.js";

describe("invitation email", () => {
  it("sends an escaped invitation with the accept link through Resend", async () => {
    const requests: RequestInit[] = [];
    const send = createResendInvitationSender({
      apiKey: "test-key",
      from: "Gradiated <hello@mail.gradiated.com>",
      fetch: async (_url, init) => {
        requests.push(init ?? {});

        return new Response(JSON.stringify({ id: "email-id" }), {
          status: 200,
        });
      },
    });
    const url = invitationUrl("https://console.gradiated.com", "tok_en-1");

    await send({
      email: "morgan@acme.com",
      invitedByEmail: "sam@acme.com",
      organizationName: "Acme <Labs>",
      role: "member",
      url,
    });

    const body = JSON.parse(String(requests[0]?.body));
    expect(url).toBe(
      "https://console.gradiated.com/invitations/accept?token=tok_en-1",
    );
    expect(body).toMatchObject({
      to: ["morgan@acme.com"],
      subject: "sam@acme.com invited you to Acme <Labs> on Gradiated",
    });
    expect(body.html).toContain("Acme &lt;Labs&gt;");
    expect(body.html).toContain(`href="${url}"`);
    expect(body.html).not.toContain("Invitation</p>");
    expect(body.text).toContain(url);
    expect(body.text).toContain("as a member");
  });
});
