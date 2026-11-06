export const CONSOLE_BASE_URL =
  import.meta.env.VITE_CONSOLE_BASE_URL ||
  (import.meta.env.DEV
    ? "http://localhost:3000"
    : "https://console.gradiated.com");

export const SAND_TO_THOUGHT_URL = "/sand-to-thought/library/";

export const ENGINEER_ENTRY_PATH = "/get-started/";

export const ENGINEER_SIGNUP_URL = new URL(
  "/login?next=engineer",
  CONSOLE_BASE_URL,
).toString();
export const ENGINEER_ORGANIZATION_SETUP_URL = new URL(
  "/onboarding?next=engineer",
  CONSOLE_BASE_URL,
).toString();
