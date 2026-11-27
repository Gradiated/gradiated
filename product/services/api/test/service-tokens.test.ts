import { expect, it, vi } from "vitest";
import {
  createServiceTokens,
  SERVICE_TOKEN_LIFETIME_SECONDS,
} from "../src/auth/service-tokens.js";

it("signs a short-lived service token for one workspace and its scopes", async () => {
  const sign = vi.fn(async () => ({ token: "signed" }));
  const workspaceId = "0198ae50-94d8-7d4d-a8be-9f9b44b8c774";

  expect(
    await createServiceTokens(sign)({ workspaceId, scopes: ["artifacts:pin"] }),
  ).toBe("signed");

  const payload = (
    sign.mock.calls[0] as unknown as [
      { body: { payload: Record<string, number | string | string[]> } },
    ]
  )[0].body.payload;
  expect(payload).toMatchObject({
    sub: "service:inference",
    ws: workspaceId,
    scopes: ["artifacts:pin"],
  });
  expect(Number(payload.exp) - Number(payload.iat)).toBe(
    SERVICE_TOKEN_LIFETIME_SECONDS,
  );
});
