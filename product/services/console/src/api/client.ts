import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

type ProblemField = keyof Pick<
  components["schemas"]["Problem"],
  "detail" | "code" | "request_id"
>;

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? "",
  credentials: "include",
});

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly requestId: string | undefined;

  constructor(status: number, body: unknown) {
    super(
      problemField(body, "detail") ?? `Request failed with status ${status}`,
    );
    this.name = "ApiError";
    this.status = status;
    this.code = problemField(body, "code");
    this.requestId = problemField(body, "request_id");
  }
}

const problemField = (
  body: unknown,
  field: ProblemField,
): string | undefined => {
  if (typeof body !== "object" || body === null) return undefined;

  const value: unknown = Reflect.get(body, field);

  return typeof value === "string" ? value : undefined;
};

export const requireData = async <T>(
  request: Promise<FetchResult<T>>,
): Promise<T> => {
  const { data, error, response } = await request;
  if (data !== undefined) return data;

  throw new ApiError(response.status, error);
};

export const requireOk = async (
  request: Promise<FetchResult<unknown>>,
): Promise<void> => {
  const { error, response } = await request;
  if (response.ok) return;

  throw new ApiError(response.status, error);
};

export const needsStaffSessionRecovery = (error: unknown) =>
  error instanceof ApiError &&
  error.status === 401 &&
  error.code === "staff_session_recovery_required";
