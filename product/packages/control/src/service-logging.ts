/** Backend diagnostics contain stable codes and stack locations, never raw error
 * messages, request bodies, headers, query strings, or customer names/emails.
 * UUID resource identifiers are allowed. */
export type ServiceLogFields = {
  request_id?: string;
  organization_id?: string | undefined;
  workspace_id?: string | undefined;
  api_key_id?: string | undefined;
  user_id?: string | undefined;
  context_source?: "authenticated_session_requested_resource";
  method?: string;
  route?: string;
  status?: number;
  duration_ms?: number;
  loop?: string;
  dependency?: string;
  attempt?: number;
  retry_ms?: number;
  signal?: string;
  error?: unknown;
};

const diagnosticCode = (error: unknown): string | undefined => {
  if (!error || typeof error !== "object" || !("code" in error)) return;
  const code = String(error.code);
  return /^(?:[A-Z0-9]{5}|E[A-Z_]{2,30}|[0-9]{1,5})$/.test(code)
    ? code
    : undefined;
};

export const createServiceLogger = (
  service: "api" | "worker",
  write: (line: string) => void = (line) => console.log(line),
  now: () => number = Date.now,
) => {
  const start = now();
  const budgets = {
    info: { windowStart: start, emitted: 0, suppressed: 0 },
    warn: { windowStart: start, emitted: 0, suppressed: 0 },
    error: { windowStart: start, emitted: 0, suppressed: 0 },
  };

  return (
    level: "info" | "warn" | "error",
    event: string,
    fields: ServiceLogFields = {},
  ): void => {
    const timestamp = now();
    const budget = budgets[level];
    if (timestamp - budget.windowStart >= 1_000) {
      budget.windowStart = timestamp;
      budget.emitted = 0;
    }
    if (budget.emitted >= 10) {
      budget.suppressed += 1;
      return;
    }
    budget.emitted += 1;

    const safe: Record<string, string | number | string[] | undefined> = {};
    for (const key of [
      "method",
      "route",
      "loop",
      "dependency",
      "signal",
    ] as const) {
      if (typeof fields[key] === "string")
        safe[key] = fields[key].slice(0, 256);
    }
    for (const key of [
      "status",
      "duration_ms",
      "attempt",
      "retry_ms",
    ] as const) {
      if (Number.isFinite(fields[key])) safe[key] = fields[key];
    }
    for (const key of [
      "request_id",
      "organization_id",
      "workspace_id",
      "api_key_id",
      "user_id",
    ] as const) {
      const value = fields[key];
      if (
        typeof value === "string" &&
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
          value,
        )
      )
        safe[key] = value;
    }
    if (fields.context_source === "authenticated_session_requested_resource")
      safe.context_source = fields.context_source;
    if (fields.error !== undefined) {
      safe.error_type =
        fields.error instanceof Error
          ? fields.error.constructor.name
          : "UnknownError";
      safe.error_code = diagnosticCode(fields.error);
      if (fields.error instanceof Error) {
        safe.error_frames = fields.error.stack
          ?.split("\n")
          .filter((line) => /^\s+at /.test(line))
          .slice(0, 8);
      }
    }

    write(
      JSON.stringify({
        timestamp: new Date(timestamp).toISOString(),
        service,
        level,
        event,
        ...safe,
        suppressed_events: budget.suppressed,
      }),
    );
    budget.suppressed = 0;
  };
};
