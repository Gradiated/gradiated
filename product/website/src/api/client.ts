import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const productApiBaseUrl =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.DEV && typeof window !== "undefined"
    ? window.location.origin
    : "https://api.gradiated.com");

export const gatewayBaseUrl =
  import.meta.env.VITE_GATEWAY_URL ??
  (import.meta.env.DEV ? "http://localhost:3002" : "https://api.gradiated.com");

export const api = createClient<paths>({
  baseUrl: productApiBaseUrl,
  credentials: "include",
});

export const requireData = async <T>(
  request: Promise<{
    data?: T;
    error?: unknown;
    response: Response;
  }>,
): Promise<T> => {
  const { data, error, response } = await request;
  if (data !== undefined) return data;

  const detail =
    error && typeof error === "object" && "detail" in error
      ? String(error.detail)
      : `Request failed with status ${response.status}.`;
  const requestError = new Error(detail) as Error & { status?: number };
  requestError.status = response.status;
  throw requestError;
};
