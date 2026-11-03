import type { ControlDatabase } from "@gradiated/control";
import { beforeEach, expect, it, vi } from "vitest";

import { StaffSessionRecoveryRequired } from "../src/auth/errors.js";
import { createAuthService } from "../src/auth/service.js";
import { createTestApp, createdOrganization } from "./support.js";

const records = vi.hoisted(() => ({
  user: [] as Record<string, unknown>[],
  session: [] as Record<string, unknown>[],
  account: [] as Record<string, unknown>[],
  verification: [] as Record<string, unknown>[],
}));

vi.mock("better-auth/adapters/drizzle", async () => {
  const { memoryAdapter } = await import("better-auth/adapters/memory");

  return { drizzleAdapter: () => memoryAdapter(records) };
});

beforeEach(() => {
  for (const rows of Object.values(records)) rows.length = 0;
});

const createHarness = () => {
  let code = "";
  const baseUrl = "http://localhost:3000";
  const auth = createAuthService({} as ControlDatabase, {
    baseUrl,
    secret: "local-only-not-secret-change-in-production-0001",
    trustedOrigins: [baseUrl],
    onUserCreated: async () => undefined,
    sendMagicLink: async () => undefined,
    sendOtp: async (message) => {
      code = message.code;
    },
  });
  const post = (path: string, body: unknown, cookie = "", origin = baseUrl) =>
    auth.handler(
      new Request(`${baseUrl}/api/auth${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: origin,
          Cookie: cookie,
        },
        body: JSON.stringify(body),
      }),
    );
  const signIn = async (email: string, extra: Record<string, unknown> = {}) => {
    expect(
      (
        await post("/email-otp/send-verification-otp", {
          email,
          type: "sign-in",
        })
      ).status,
    ).toBe(200);
    const response = await post("/sign-in/email-otp", {
      email,
      otp: code,
      name: "Test user",
      ...extra,
    });
    expect(response.status).toBe(200);
    const user = records.user.find((item) => item.email === email)!;
    return { user, cookie: mergeCookies("", response) };
  };

  return { auth, post, signIn };
};

const mergeCookies = (previous: string, response: Response) => {
  const cookies = new Map(
    previous
      .split("; ")
      .filter(Boolean)
      .map((entry) => [
        entry.slice(0, entry.indexOf("=")),
        entry.slice(entry.indexOf("=") + 1),
      ]),
  );
  for (const entry of response.headers.getSetCookie()) {
    const cookie = entry.split(";")[0]!;
    cookies.set(
      cookie.slice(0, cookie.indexOf("=")),
      cookie.slice(cookie.indexOf("=") + 1),
    );
  }

  return [...cookies].map(([name, value]) => `${name}=${value}`).join("; ");
};

it("prevents self-elevation and checks staff revocation against the current user record", async () => {
  const { auth, post, signIn } = createHarness();
  const email = "staff-test@example.com";
  const { cookie } = await signIn(email, { isStaff: true, is_staff: true });
  expect(records.user[0]?.isStaff).toBe(false);
  const headers = new Headers({ Cookie: cookie });
  expect(await auth.resolveSession(headers)).toMatchObject({
    email,
    isStaff: false,
  });

  const update = await post(
    "/update-user",
    { isStaff: true, is_staff: true },
    cookie,
  );
  expect(update.status).toBe(400);
  expect(records.user[0]?.isStaff).toBe(false);
  expect(await auth.resolveSession(headers)).toMatchObject({ isStaff: false });

  const provision = vi.fn(async () => createdOrganization);
  const app = createTestApp({
    auth,
    services: { organizations: { createForUser: provision } },
  });
  const createOrganization = () =>
    app.request("/api/v1/admin/organizations", {
      method: "POST",
      headers: {
        Cookie: cookie,
        "Content-Type": "application/json",
        "X-Is-Staff": "true",
      },
      body: JSON.stringify({ name: "Customer" }),
    });
  expect((await createOrganization()).status).toBe(403);
  expect(provision).not.toHaveBeenCalled();

  records.user[0]!.isStaff = true;
  expect((await createOrganization()).status).toBe(201);
  expect(provision).toHaveBeenCalledTimes(1);

  records.user[0]!.isStaff = false;
  expect((await createOrganization()).status).toBe(403);
  expect(provision).toHaveBeenCalledTimes(1);
});

it("switches a staff session to a customer, denies nesting and staff targets, then restores the original session", async () => {
  const { auth, post, signIn } = createHarness();
  const staff = await signIn("staff@example.com");
  const target = await signIn("customer@example.com");
  const body = { user_id: target.user.id };
  expect(
    (await post("/staff/impersonate-user", body, staff.cookie)).status,
  ).toBe(403);
  staff.user.isStaff = true;
  expect(
    (
      await post(
        "/staff/impersonate-user",
        body,
        staff.cookie,
        "https://evil.example",
      )
    ).status,
  ).toBe(403);
  expect(
    (
      await post(
        "/staff/impersonate-user",
        { user_id: staff.user.id },
        staff.cookie,
      )
    ).status,
  ).toBe(403);
  target.user.isStaff = true;
  expect(
    (await post("/staff/impersonate-user", body, staff.cookie)).status,
  ).toBe(403);
  target.user.isStaff = false;
  target.user.emailVerified = false;
  expect(
    (await post("/staff/impersonate-user", body, staff.cookie)).status,
  ).toBe(403);
  target.user.emailVerified = true;
  expect(
    (await post("/staff/stop-impersonating", {}, target.cookie)).status,
  ).toBe(401);

  const app = createTestApp({ auth });
  const started = await app.request("/api/v1/admin/impersonations", {
    method: "POST",
    headers: {
      Cookie: staff.cookie,
      Origin: "http://localhost:3000",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  expect(started.status).toBe(200);
  expect(await started.clone().json()).toEqual(body);
  const cookie = mergeCookies(staff.cookie, started);
  expect(
    await auth.resolveSession(new Headers({ Cookie: cookie })),
  ).toMatchObject({
    id: target.user.id,
    isStaff: false,
    impersonatedBy: staff.user.id,
  });
  expect((await post("/staff/impersonate-user", body, cookie)).status).toBe(
    403,
  );
  const impersonated = records.session.find(
    (item) => item.impersonatedBy === staff.user.id,
  )!;
  expect(
    new Date(impersonated.expiresAt as Date).getTime() - Date.now(),
  ).toBeLessThanOrEqual(15 * 60 * 1000);

  expect(
    (
      await post(
        "/staff/stop-impersonating",
        {},
        cookie,
        "https://evil.example",
      )
    ).status,
  ).toBe(403);
  const stopped = await app.request("/api/v1/admin/impersonations/stop", {
    method: "POST",
    headers: { Cookie: cookie, Origin: "http://localhost:3000" },
  });
  expect(stopped.status).toBe(200);
  expect(
    await auth.resolveSession(
      new Headers({ Cookie: mergeCookies(cookie, stopped) }),
    ),
  ).toMatchObject({ id: staff.user.id, isStaff: true, impersonatedBy: null });
  expect(records.session.some((item) => item.id === impersonated.id)).toBe(
    false,
  );
});

it.each([
  "staff_revoked",
  "staff_unverified",
  "original_session_revoked",
  "target_promoted",
  "target_unverified",
])("invalidates impersonation when %s", async (change) => {
  const { auth, post, signIn } = createHarness();
  const staff = await signIn("staff@example.com");
  const target = await signIn("customer@example.com");
  staff.user.isStaff = true;
  const started = await post(
    "/staff/impersonate-user",
    { user_id: target.user.id },
    staff.cookie,
  );
  expect(started.status).toBe(200);
  const cookie = mergeCookies(staff.cookie, started);
  if (change === "staff_revoked") staff.user.isStaff = false;
  if (change === "staff_unverified") staff.user.emailVerified = false;
  if (change === "target_unverified") target.user.emailVerified = false;
  if (change === "target_promoted") target.user.isStaff = true;
  if (change === "original_session_revoked") {
    const originalIndex = records.session.findIndex(
      (item) => item.userId === staff.user.id,
    );
    records.session.splice(originalIndex, 1);
  }

  expect(await auth.resolveSession(new Headers({ Cookie: cookie }))).toBeNull();
  expect(
    (await post("/update-user", { name: "Not allowed" }, cookie)).status,
  ).toBe(401);
  expect((await post("/staff/stop-impersonating", {}, cookie)).status).toBe(
    change === "original_session_revoked" ? 401 : 200,
  );
});

it("can restore the staff account after the impersonation expires", async () => {
  const { auth, post, signIn } = createHarness();
  const staff = await signIn("staff@example.com");
  const target = await signIn("customer@example.com");
  staff.user.isStaff = true;
  const started = await post(
    "/staff/impersonate-user",
    { user_id: target.user.id },
    staff.cookie,
  );
  expect(started.status).toBe(200);
  const cookie = mergeCookies(staff.cookie, started);
  const impersonated = records.session.find(
    (item) => item.impersonatedBy === staff.user.id,
  )!;
  impersonated.expiresAt = new Date(Date.now() - 1000);
  await expect(
    auth.resolveSession(new Headers({ Cookie: cookie })),
  ).rejects.toBeInstanceOf(StaffSessionRecoveryRequired);
  const stopped = await post("/staff/stop-impersonating", {}, cookie);
  expect(stopped.status).toBe(200);
  expect(
    await auth.resolveSession(
      new Headers({ Cookie: mergeCookies(cookie, stopped) }),
    ),
  ).toMatchObject({ id: staff.user.id, isStaff: true });
});

it.each(["active", "expired", "staff_revoked"])(
  "sign-out revokes both staff and impersonation sessions when %s",
  async (state) => {
    const { auth, post, signIn } = createHarness();
    const staff = await signIn("staff@example.com");
    const target = await signIn("customer@example.com");
    staff.user.isStaff = true;
    const started = await post(
      "/staff/impersonate-user",
      { user_id: target.user.id },
      staff.cookie,
    );
    expect(started.status).toBe(200);
    const cookie = mergeCookies(staff.cookie, started);
    const impersonated = records.session.find(
      (item) => item.impersonatedBy === staff.user.id,
    )!;
    if (state === "expired")
      impersonated.expiresAt = new Date(Date.now() - 1000);
    if (state === "staff_revoked") staff.user.isStaff = false;

    const signedOut = await post("/sign-out", {}, cookie);
    expect(signedOut.status).toBe(200);
    expect(
      records.session.some(
        (item) => item.userId === staff.user.id || item.id === impersonated.id,
      ),
    ).toBe(false);
    expect(
      await auth.resolveSession(new Headers({ Cookie: staff.cookie })),
    ).toBeNull();
    expect(
      await auth.resolveSession(new Headers({ Cookie: cookie })),
    ).toBeNull();
    expect((await post("/staff/stop-impersonating", {}, cookie)).status).toBe(
      401,
    );
    expect(
      (
        await post(
          "/staff/stop-impersonating",
          {},
          mergeCookies(cookie, signedOut),
        )
      ).status,
    ).toBe(401);
    expect(
      await auth.resolveSession(new Headers({ Cookie: target.cookie })),
    ).toMatchObject({ id: target.user.id });
  },
);

it("does not revoke the retained staff session on a cross-site sign-out attempt", async () => {
  const { auth, post, signIn } = createHarness();
  const staff = await signIn("staff@example.com");
  const target = await signIn("customer@example.com");
  staff.user.isStaff = true;
  const started = await post(
    "/staff/impersonate-user",
    { user_id: target.user.id },
    staff.cookie,
  );
  expect(started.status).toBe(200);
  const cookie = mergeCookies(staff.cookie, started);
  expect(
    (await post("/sign-out", {}, cookie, "https://evil.example")).status,
  ).toBe(403);
  expect(
    await auth.resolveSession(new Headers({ Cookie: staff.cookie })),
  ).toMatchObject({ id: staff.user.id });
  expect(
    await auth.resolveSession(new Headers({ Cookie: cookie })),
  ).toMatchObject({ id: target.user.id });
});

it("enforces an absolute 15-minute impersonation deadline even if session expiry is extended", async () => {
  const { auth, post, signIn } = createHarness();
  const staff = await signIn("staff@example.com");
  const target = await signIn("customer@example.com");
  staff.user.isStaff = true;
  const started = await post(
    "/staff/impersonate-user",
    { user_id: target.user.id },
    staff.cookie,
  );
  expect(started.status).toBe(200);
  const cookie = mergeCookies(staff.cookie, started);
  const impersonated = records.session.find(
    (item) => item.impersonatedBy === staff.user.id,
  )!;
  const expiresAt = new Date(impersonated.expiresAt as Date);
  const createdAt = new Date(impersonated.createdAt as Date);
  expect(expiresAt.getTime() - createdAt.getTime()).toBeGreaterThan(
    14 * 60 * 1000,
  );
  expect(expiresAt.getTime() - createdAt.getTime()).toBeLessThanOrEqual(
    15 * 60 * 1000,
  );
  const resolved = await auth.resolveSession(new Headers({ Cookie: cookie }));
  expect(resolved?.impersonationExpiresAt).toEqual(
    new Date(
      Math.min(expiresAt.getTime(), createdAt.getTime() + 15 * 60 * 1000),
    ),
  );
  impersonated.createdAt = new Date(Date.now() - 15 * 60 * 1000 - 1);
  impersonated.expiresAt = new Date(Date.now() + 60 * 60 * 1000);
  await expect(
    auth.resolveSession(new Headers({ Cookie: cookie })),
  ).rejects.toBeInstanceOf(StaffSessionRecoveryRequired);
  const stopped = await post("/staff/stop-impersonating", {}, cookie);
  expect(stopped.status).toBe(200);
  expect(
    await auth.resolveSession(
      new Headers({ Cookie: mergeCookies(cookie, stopped) }),
    ),
  ).toMatchObject({ id: staff.user.id, isStaff: true });
});

it.each(["expired_row", "absolute_deadline", "missing_active_cookie"])(
  "signals retained staff recovery on a cold bootstrap after %s",
  async (state) => {
    const { auth, post, signIn } = createHarness();
    const staff = await signIn("staff@example.com");
    const target = await signIn("customer@example.com");
    staff.user.isStaff = true;
    const started = await post(
      "/staff/impersonate-user",
      { user_id: target.user.id },
      staff.cookie,
    );
    expect(started.status).toBe(200);
    let cookie = mergeCookies(staff.cookie, started);
    const impersonated = records.session.find(
      (item) => item.impersonatedBy === staff.user.id,
    )!;
    if (state === "expired_row")
      impersonated.expiresAt = new Date(Date.now() - 1000);
    if (state === "absolute_deadline")
      impersonated.createdAt = new Date(Date.now() - 15 * 60_000 - 1000);
    if (state === "missing_active_cookie")
      cookie = cookie
        .split("; ")
        .filter((entry) => entry.includes("staff_session="))
        .join("; ");
    const app = createTestApp({
      auth,
      services: { organizations: { listForUser: async () => [] } },
    });

    const bootstrap = await app.request("/api/v1/me", {
      headers: { Cookie: cookie },
    });
    expect(bootstrap.status).toBe(401);
    expect(await bootstrap.json()).toMatchObject({
      code: "staff_session_recovery_required",
    });
    const restored = await app.request("/api/v1/admin/impersonations/stop", {
      method: "POST",
      headers: { Cookie: cookie, Origin: "http://localhost:3000" },
    });
    expect(restored.status).toBe(200);
    const recovered = await app.request("/api/v1/me", {
      headers: { Cookie: mergeCookies(cookie, restored) },
    });
    expect(recovered.status).toBe(200);
    expect(await recovered.json()).toMatchObject({
      id: staff.user.id,
      is_staff: true,
      impersonated_by: null,
    });
  },
);
