const DEFAULT_TIMEOUT_MS = 30_000;

export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | undefined,
    message: string,
  ) {
    super(message);
    this.name = "HttpError";
  }
}

export interface HttpResponse {
  status: number;
  headers: Headers;
  body: unknown;
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.length === 0) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function extractErrorBody(body: unknown): string {
  if (body !== null && typeof body === "object") {
    const problem = body as {
      detail?: unknown;
      message?: unknown;
      error?: unknown;
    };
    for (const candidate of [problem.detail, problem.message, problem.error]) {
      if (typeof candidate === "string" && candidate.length > 0) {
        return candidate;
      }
    }
  }
  if (typeof body === "string" && body.length > 0) {
    return body.slice(0, 500);
  }
  return "No error details were returned.";
}

export async function request(
  url: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<HttpResponse> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(url, { ...rest, signal: controller.signal });
  } catch (error) {
    const reason =
      error instanceof Error && error.name === "AbortError"
        ? "The request timed out."
        : error instanceof Error
          ? error.message
          : "The request failed.";
    throw new HttpError(0, "network", reason);
  } finally {
    clearTimeout(timer);
  }

  const body = await parseBody(response);
  if (!response.ok) {
    throw new HttpError(
      response.status,
      response.headers.get("content-type")?.includes("application/problem+json")
        ? ((body as { code?: string })?.code ?? undefined)
        : undefined,
      extractErrorBody(body),
    );
  }
  return { status: response.status, headers: response.headers, body };
}
