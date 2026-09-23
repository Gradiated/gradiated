import { requestFailure, WizardError } from "./errors.js";
import { isRecord } from "./guards.js";
import { HttpStatusError, request, type HttpResponse } from "./http.js";
import * as ui from "./ui.js";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const CODE_PATTERN = /^\d{6}$/;
const NANO_USD_PER_USD = 1_000_000_000;

export type AccountMode = "signup" | "login";

interface AuthTarget {
  apiBaseUrl: string;
  origin: string;
}

interface KeyResponse {
  secret: string;
  balanceNanoUsd: number | null;
}

const askTrimmed = async (
  message: string,
  pattern: RegExp,
  hint: string,
): Promise<string> => {
  const value = await ui.askText(message, (input) =>
    pattern.test(input.trim()) ? undefined : hint,
  );

  return value.trim();
};

// Node fetch has no cookie jar. The session stays in memory, and only the
// name/value pairs are forwarded to key creation on the same API.
const sessionCookie = (response: HttpResponse): string => {
  // Older Node 18 releases expose several cookies as one combined header.
  const cookies =
    typeof response.headers.getSetCookie === "function"
      ? response.headers.getSetCookie()
      : (response.headers.get("set-cookie") ?? "").split(/,(?=\s*[^;,=\s]+=)/);

  const pairs = cookies
    .map((cookie) => cookie.split(";")[0]?.trim())
    .filter(Boolean)
    .join("; ");
  if (pairs.length === 0) {
    throw new WizardError(
      "Sign-in did not return a session cookie. Run the wizard again.",
    );
  }

  return pairs;
};

const isRejectedCode = (error: unknown): boolean =>
  error instanceof HttpStatusError &&
  (error.status === 400 || error.status === 401 || error.status === 422);

const sendCode = async (target: AuthTarget, email: string): Promise<void> => {
  try {
    await request(
      `${target.apiBaseUrl}/api/auth/email-otp/send-verification-otp`,
      {
        method: "POST",
        headers: { "content-type": "application/json", origin: target.origin },
        body: JSON.stringify({ email, type: "sign-in" }),
        redirect: "error",
      },
    );
  } catch (error) {
    throw requestFailure("Could not send the verification code", error);
  }
};

const verifyCode = async (
  target: AuthTarget,
  email: string,
  code: string,
): Promise<string> => {
  let response: HttpResponse;
  try {
    response = await request(
      `${target.apiBaseUrl}/api/auth/sign-in/email-otp`,
      {
        method: "POST",
        headers: { "content-type": "application/json", origin: target.origin },
        body: JSON.stringify({ email, otp: code }),
        redirect: "error",
      },
    );
  } catch (error) {
    if (!isRejectedCode(error)) {
      throw requestFailure("Could not verify the code", error);
    }

    throw new WizardError(
      "The code was rejected. Run the wizard and request a new one.",
      { cause: error },
    );
  }

  return sessionCookie(response);
};

const parseKeyResponse = (body: unknown): KeyResponse => {
  if (
    !isRecord(body) ||
    typeof body.secret !== "string" ||
    body.secret.length === 0
  ) {
    throw new WizardError("The key response did not include a secret.");
  }

  return {
    secret: body.secret,
    balanceNanoUsd:
      typeof body.balance_nano_usd === "number" ? body.balance_nano_usd : null,
  };
};

const createKey = async (
  target: AuthTarget,
  cookie: string,
): Promise<KeyResponse> => {
  let response: HttpResponse;
  try {
    response = await request(`${target.apiBaseUrl}/api/v1/wizard/key`, {
      method: "POST",
      headers: { cookie, origin: target.origin },
      redirect: "error",
    });
  } catch (error) {
    throw requestFailure("Could not create an API key", error);
  }

  return parseKeyResponse(response.body);
};

const reportAccount = (
  mode: AccountMode,
  balanceNanoUsd: number | null,
): void => {
  ui.success(mode === "signup" ? "Account ready." : "Logged in.");

  if (balanceNanoUsd !== null && (mode === "signup" || balanceNanoUsd > 0)) {
    ui.info(
      `Current balance: $${(balanceNanoUsd / NANO_USD_PER_USD).toFixed(2)} (from the API).`,
    );
  }
};

export const signIn = async (
  apiBaseUrl: string,
  mode: AccountMode,
): Promise<string> => {
  // Node fetch sends Fetch Metadata but no Origin, and Better Auth requires a
  // trusted origin for these requests, as it does for the console.
  const target = { apiBaseUrl, origin: new URL(apiBaseUrl).origin };
  const email = await askTrimmed(
    "Email:",
    EMAIL_PATTERN,
    "Enter a valid email address.",
  );

  await ui.step(
    "Requesting a verification code",
    () => sendCode(target, email),
    { done: () => "Code sent", failed: () => "Could not send the code" },
  );
  ui.note(
    `Check ${email} for a six-digit code. It expires in 10 minutes.`,
    "Email sent",
  );

  const code = await askTrimmed(
    "Code:",
    CODE_PATTERN,
    "Enter the six-digit code.",
  );
  const cookie = await ui.step(
    "Verifying the code",
    () => verifyCode(target, email, code),
    { done: () => "Verified", failed: () => "Verification failed" },
  );
  const key = await ui.step(
    "Creating your local API key",
    () => createKey(target, cookie),
    { done: () => "Key created", failed: () => "Key creation failed" },
  );

  reportAccount(mode, key.balanceNanoUsd);

  return key.secret;
};
