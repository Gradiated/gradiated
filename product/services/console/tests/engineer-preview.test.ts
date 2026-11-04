import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  beginEngineerPreview,
  completeEngineerPreview,
  getEngineerPreviewUser,
  isEngineerPreview,
  saveEngineerPreviewOrganization,
} from "@/lib/engineer-preview";

const postMessage = vi.fn();

beforeEach(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  });
  vi.stubGlobal("window", {
    location: { search: "?next=engineer&preview=engineer" },
    parent: { postMessage },
  });
  vi.stubEnv("DEV", true);
  vi.stubEnv("VITE_WEBSITE_URL", "http://localhost:5173");
  postMessage.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("existing account screens in the local engineer demo", () => {
  it("requires organization setup before handing the account to the wizard", () => {
    beginEngineerPreview("alex@acme.example", "Alex Morgan");
    expect(
      getEngineerPreviewUser().organizations[0]?.onboarding_completed,
    ).toBe(false);
    expect(() => completeEngineerPreview()).toThrow(
      "Finish organization setup first.",
    );
    expect(postMessage).not.toHaveBeenCalled();
  });

  it("hands off the actual entered account and organization after setup", () => {
    beginEngineerPreview("alex@acme.example", "Alex Morgan");
    const organization = saveEngineerPreviewOrganization(
      "Acme Engineers",
      false,
    );
    const user = getEngineerPreviewUser();
    completeEngineerPreview();

    expect(organization.onboarding_completed).toBe(true);
    expect(organization.auto_join_domain).toBeNull();
    expect(postMessage).toHaveBeenCalledWith(
      {
        type: "gradiated:engineer-preview-account",
        account: {
          userId: user.id,
          organizationId: organization.id,
          name: "Alex Morgan",
          email: "alex@acme.example",
          company: "Acme Engineers",
        },
      },
      "http://localhost:5173",
    );
  });

  it("does not enable simulated account operations in production", () => {
    vi.stubEnv("DEV", false);
    expect(isEngineerPreview()).toBe(false);
    expect(() => beginEngineerPreview("alex@acme.example")).toThrow(
      "Account preview is unavailable.",
    );
    expect(() => getEngineerPreviewUser()).toThrow(
      "Account preview is unavailable.",
    );
  });

  it("does not use a stored demo account on a normal sign-in route", () => {
    beginEngineerPreview("alex@acme.example");
    vi.stubGlobal("window", {
      location: { search: "?next=engineer" },
      parent: { postMessage },
    });
    expect(isEngineerPreview()).toBe(false);
    expect(() => getEngineerPreviewUser()).toThrow(
      "Account preview is unavailable.",
    );
  });
});
