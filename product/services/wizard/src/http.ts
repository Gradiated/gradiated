import { isRecord } from "./guards.js";

const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_DETAIL_LENGTH = 500;

export class HttpStatusError extends Error {
  constructor(
    readonly status: number,
    readonly problemCode: string | undefined,
    readonly detail: string,
  ) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "HttpStatusError";
  }
}

export class NetworkError extends Error {
  constructor(
    readonly reason: "timeout" | "failure",
    options: { cause: unknown },
  ) {
    super(
      reason === "timeout"
        ? "The request timed out."
        : "The request could not reach the server.",
      options,
    );
    this.name = "NetworkError";
  }
}

export interface HttpResponse {
  headers: Headers;
  body: unknown;
}

const parseBody = async (response: Response): Promise<unknown> => {
  const text = await response.text();
  if (text.length === 0) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
};

const errorDetail = (body: unknown): string => {
  if (isRecord(body)) {
    for (const candidate of [body.detail, body.message, body.error]) {
      if (typeof candidate === "string" && candidate.length > 0) {
        return candidate;
      }
    }
  }

  if (typeof body === "string" && body.length > 0) {
    return body.slice(0, MAX_DETAIL_LENGTH);
  }

  return "No error details were returned.";
};

const problemCode = (response: Response, body: unknown): string | undefined => {
  const isProblem = response.headers
    .get("content-type")
    ?.includes("application/problem+json");

  return isProblem && isRecord(body) && typeof body.code === "string"
    ? body.code
    : undefined;
};

export const request = async (
  url: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<HttpResponse> => {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  let body: unknown;
  try {
    response = await fetch(url, { ...rest, signal: controller.signal });
    body = await parseBody(response);
  } catch (error) {
    const reason = controller.signal.aborted ? "timeout" : "failure";
    throw new NetworkError(reason, { cause: error });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new HttpStatusError(
      response.status,
      problemCode(response, body),
      errorDetail(body),
    );
  }

  return { headers: response.headers, body };
};
