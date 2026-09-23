export class ControlServiceError extends Error {
  constructor(
    readonly code: "forbidden" | "not_found" | "unavailable",
    message: string,
    override readonly cause?: unknown,
  ) {
    super(message);
    this.name = "ControlServiceError";
  }
}
