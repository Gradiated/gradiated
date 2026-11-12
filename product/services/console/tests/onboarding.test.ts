import { describe, expect, it } from "vitest";

import type { CurrentUser } from "@/api/queries";
import {
  organizationToOnboard,
  suggestedOrganizationName,
} from "@/lib/onboarding";

const organization = (
  patch: Partial<CurrentUser["organizations"][number]>,
): CurrentUser["organizations"][number] => ({
  id: "00000000-0000-4000-8000-000000000001",
  name: "Personal",
  slug: "personal",
  status: "active",
  role: "admin",
  default_workspace_id: "00000000-0000-4000-8000-000000000002",
  auto_join_domain: null,
  onboarding_completed: false,
  ...patch,
});

const userWith = (
  ...organizations: CurrentUser["organizations"]
): CurrentUser => ({
  id: "user",
  name: "Alex",
  email: "alex@acme.com",
  email_verified: true,
  impersonation_expires_at: null as string | null,
  impersonated_by: null,
  is_staff: false,
  company_email_domain: "acme.com",
  image_url: null,
  created_at: "2026-10-14T00:00:00Z",
  organizations,
});

describe("onboarding", () => {
  it("asks admins to set up an organization they have not finished", () => {
    const pending = organization({ id: "pending" });

    expect(
      organizationToOnboard(
        userWith(organization({ onboarding_completed: true }), pending),
      ),
    ).toBe(pending);
  });

  it("skips members who joined someone else's organization", () => {
    expect(
      organizationToOnboard(userWith(organization({ role: "member" }))),
    ).toBeUndefined();
    expect(organizationToOnboard(undefined)).toBeUndefined();
  });

  it.each([
    ["acme.com", "Acme"],
    ["acme.co.uk", "Acme"],
    [null, ""],
  ])("suggests a name from %s", (domain, name) => {
    expect(suggestedOrganizationName(domain)).toBe(name);
  });
});
