import { HttpStatusError, NetworkError } from "./http.js";

export class WizardError extends Error {
  constructor(message: string, options?: { cause: unknown }) {
    super(message, options);
    this.name = "WizardError";
  }
}

export const requestFailure = (action: string, error: unknown): unknown => {
  if (error instanceof HttpStatusError) {
    return new WizardError(`${action} (${error.status}): ${error.detail}`, {
      cause: error,
    });
  }

  if (error instanceof NetworkError) {
    return new WizardError(`${action}: ${error.message}`, { cause: error });
  }

  return error;
};

export const diagnosticCode = (error: unknown): string | undefined => {
  if (error instanceof HttpStatusError) {
    return error.problemCode ?? `http_${error.status}`;
  }
  if (error instanceof NetworkError) return `network_${error.reason}`;
  if (error instanceof Error && "code" in error) return String(error.code);

  return undefined;
};

export const failureMessage = (error: unknown): string => {
  if (!(error instanceof Error)) return "Unexpected failure.";

  const code = diagnosticCode(
    error instanceof WizardError ? error.cause : error,
  );

  return code === undefined ? error.message : `${error.message} (${code})`;
};
