export class ControlServiceError extends Error {
  constructor(
    readonly code: "forbidden" | "not_found" | "unavailable" | "conflict",
    message: string,
    override readonly cause?: unknown,
  ) {
    super(message);
    this.name = "ControlServiceError";
  }
}

/** Whether a database error, or any error it wraps, violates the named constraint. */
export const violatesConstraint = (
  error: unknown,
  constraint: string,
): boolean => {
  if (!error || typeof error !== "object") return false;
  if ("constraint" in error && error.constraint === constraint) return true;

  return (
    "cause" in error &&
    error.cause !== error &&
    violatesConstraint(error.cause, constraint)
  );
};
