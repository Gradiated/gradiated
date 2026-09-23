export const httpStatus = (error: unknown): number | undefined => {
  if (typeof error !== "object" || error === null || !("status" in error)) {
    return undefined;
  }

  return typeof error.status === "number" ? error.status : undefined;
};

export const isClientError = (error: unknown): boolean => {
  const status = httpStatus(error);
  return status !== undefined && status >= 400 && status < 500;
};

export const errorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error && error.message ? error.message : fallback;
