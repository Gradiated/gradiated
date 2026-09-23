import { describe, expect, vi } from "vitest";
import { signIn } from "../src/account.js";
import * as ui from "../src/ui.js";
import { KEY_SECRET, SEND_CODE_PATH } from "./support/auth-stub.js";
import { test as it } from "./support/better-auth-server.js";

vi.mock("../src/ui.js", () => import("./support/ui-stub.js"));

describe("wizard with real Better Auth origin and session checks", () => {
  it("rejects a request without Origin before sending an email", async ({
    betterAuthServer: { baseUrl, activity },
  }) => {
    const response = await fetch(`${baseUrl}${SEND_CODE_PATH}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: "person@example.com", type: "sign-in" }),
    });

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({
      message: "Missing or null Origin",
    });
    expect(activity.deliveries).toBe(0);
  });

  it("signs up and logs back in through OTP and authenticates key creation", async ({
    betterAuthServer: { baseUrl, activity },
  }) => {
    vi.mocked(ui.askText).mockImplementation(async (prompt) =>
      prompt === "Email:" ? "person@example.com" : activity.code,
    );

    expect(await signIn(baseUrl, "signup")).toBe(KEY_SECRET);
    expect(await signIn(baseUrl, "login")).toBe(KEY_SECRET);
    expect(activity.deliveries).toBe(2);
    expect(activity.keyRequests).toBe(2);
    expect(activity.signedInUsers[0]).toBeTruthy();
    expect(activity.signedInUsers[0]).toBe(activity.signedInUsers[1]);
  });
});
