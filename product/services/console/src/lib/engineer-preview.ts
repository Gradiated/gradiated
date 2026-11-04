import { z } from "zod";
import type { CurrentUser } from "@/api/queries";
import { engineerOnboardingUrl } from "./engineer-onboarding";

const storageKey = "gradiated-engineer-signup-preview-v1";
const recordSchema = z.object({
  userId: z.string().uuid(),
  organizationId: z.string().uuid(),
  workspaceId: z.string().uuid(),
  name: z.string().min(1).max(100),
  email: z.email(),
  company: z.string().max(200),
  completed: z.boolean(),
  autoJoin: z.boolean(),
});

export const isEngineerPreview = () =>
  import.meta.env.DEV &&
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("preview") === "engineer";

const requirePreview = () => {
  if (!isEngineerPreview()) throw new Error("Account preview is unavailable.");
};

const readRecord = () => {
  requirePreview();
  return recordSchema.parse(
    JSON.parse(sessionStorage.getItem(storageKey) ?? "null"),
  );
};

export const beginEngineerPreview = (
  email: string,
  name = email.split("@")[0],
) => {
  requirePreview();
  const record = recordSchema.parse({
    userId: crypto.randomUUID(),
    organizationId: crypto.randomUUID(),
    workspaceId: crypto.randomUUID(),
    name,
    email,
    company: "Personal",
    completed: false,
    autoJoin: true,
  });
  sessionStorage.setItem(storageKey, JSON.stringify(record));
};

export const engineerPreviewOrganizationPath =
  "/onboarding?next=engineer&preview=engineer";
export const engineerPreviewLoginPath = "/login?next=engineer&preview=engineer";

export const getEngineerPreviewUser = (): CurrentUser => {
  const record = readRecord();
  const domain = record.email.split("@")[1] ?? "";
  const companyDomain = [
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "yahoo.com",
    "proton.me",
  ].includes(domain)
    ? null
    : domain;

  return {
    id: record.userId,
    name: record.name,
    email: record.email,
    email_verified: true,
    is_staff: false,
    impersonated_by: null,
    impersonation_expires_at: null,
    company_email_domain: companyDomain,
    image_url: null,
    created_at: "2026-11-03T00:00:00Z",
    organizations: [
      {
        id: record.organizationId,
        name: record.company,
        status: "active",
        role: "admin",
        default_workspace_id: record.workspaceId,
        auto_join_domain: record.autoJoin ? companyDomain : null,
        onboarding_completed: record.completed,
      },
    ],
  };
};

export const saveEngineerPreviewOrganization = (
  company: string,
  autoJoin: boolean,
): CurrentUser["organizations"][number] => {
  const record = readRecord();
  sessionStorage.setItem(
    storageKey,
    JSON.stringify({ ...record, company, autoJoin, completed: true }),
  );

  const [organization] = getEngineerPreviewUser().organizations;
  if (!organization) throw new Error("Preview organization is missing.");

  return organization;
};

export const completeEngineerPreview = () => {
  const record = readRecord();
  if (!record.completed) throw new Error("Finish organization setup first.");

  window.parent.postMessage(
    {
      type: "gradiated:engineer-preview-account",
      account: {
        userId: record.userId,
        organizationId: record.organizationId,
        name: record.name,
        email: record.email,
        company: record.company,
      },
    },
    new URL(engineerOnboardingUrl()).origin,
  );
};

export const clearEngineerPreview = () => {
  requirePreview();
  sessionStorage.removeItem(storageKey);
};
