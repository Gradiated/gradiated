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
