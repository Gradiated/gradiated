export const CONSOLE_BASE_URL =
  import.meta.env.VITE_CONSOLE_BASE_URL ||
  (import.meta.env.DEV
    ? "http://localhost:3000"
    : "https://console.gradiated.com");

export const SAND_TO_THOUGHT_URL = "/sand-to-thought/";
