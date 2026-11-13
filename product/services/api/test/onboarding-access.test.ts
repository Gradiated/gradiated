import { describe, expect, it, vi } from "vitest";

import { requireOnboardingAdmin } from "../src/http/onboarding-access.js";
import type { SessionUser } from "../src/types.js";
import { organizationId, organizationSummary, user } from "./support.js";

const context = (session: SessionUser | null) => ({
  get: () => async () => session,
});
const organizations = (membership = organizationSummary) => ({
  listForUser: vi.fn(async () => [membership]),
});

describe("engineer onboarding access", () => {
  it("returns the organization and signer bound to the session", async () => {
    await expect(
      requireOnboardingAdmin(context(user), organizations(), organizationId),
    ).resolves.toEqual({
      organization: organizationSummary,
      owner: { userId: user.id, email: user.email, organizationId },
    });
  });

  it("rejects impersonation before reading memberships", async () => {
    const memberships = organizations();
    await expect(
      requireOnboardingAdmin(
        context({ ...user, impersonatedBy: "staff-user" }),
        memberships,
        organizationId,
      ),
    ).rejects.toMatchObject({ problem: { status: 403 } });
    expect(memberships.listForUser).not.toHaveBeenCalled();
  });

  it.each([
    { session: { ...user, emailVerified: false } },
    { membership: { ...organizationSummary, role: "member" as const } },
    { membership: { ...organizationSummary, status: "suspended" as const } },
    {
      membership: {
        ...organizationSummary,
        id: "0198ae59-294a-73a9-9d2f-962449d34227",
      },
    },
  ])(
    "requires a verified admin of the active organization: %j",
    async ({ session = user, membership = organizationSummary }) => {
      await expect(
        requireOnboardingAdmin(
          context(session),
          organizations(membership),
          organizationId,
        ),
      ).rejects.toMatchObject({ problem: { status: 403 } });
    },
  );

  it("requires a session", async () => {
    await expect(
      requireOnboardingAdmin(context(null), organizations(), organizationId),
    ).rejects.toMatchObject({ problem: { status: 401 } });
  });
});
