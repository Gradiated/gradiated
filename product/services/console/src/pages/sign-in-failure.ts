export type SignInMethod = "github" | "google" | "magic_link";

const DIAGNOSTIC_CODE = /^[A-Za-z0-9_]{1,64}$/;

const diagnosticCode = (value: unknown): string | undefined =>
  typeof value === "string" && DIAGNOSTIC_CODE.test(value) ? value : undefined;

export const signInFailureCode = (failure: unknown): string => {
  if (failure instanceof Error) return failure.name;
  if (typeof failure !== "object" || failure === null) return typeof failure;

  const code = diagnosticCode(Reflect.get(failure, "code"));
  if (code) return code;

  const status: unknown = Reflect.get(failure, "status");

  return typeof status === "number" ? `http_${status}` : "unknown";
};

export const callbackErrorCode = (value: string): string =>
  diagnosticCode(value) ?? "unrecognized";

export const logSignInFailure = (method: SignInMethod, failure: unknown) => {
  console.error("sign_in_failed", method, signInFailureCode(failure));
};

export const logSignInCallbackFailure = (value: string) => {
  console.error("sign_in_callback_failed", callbackErrorCode(value));
};
