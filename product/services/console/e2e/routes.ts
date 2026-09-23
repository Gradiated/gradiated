import type { Route } from "@playwright/test";

export const fulfillJson = (route: Route, body: unknown) =>
  route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(body),
  });

export const fulfillProblem = (route: Route, status: number, detail: string) =>
  route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({
      type: "about:blank",
      title: "Request failed",
      status,
      detail,
      code: "internal_error",
      request_id: "playwright",
    }),
  });

export const apiPathEndsWith =
  (suffix: string) =>
  (url: URL): boolean =>
    url.pathname.startsWith("/api/v1/") && url.pathname.endsWith(suffix);
