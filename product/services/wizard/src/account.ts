import { HttpError, request } from "./http.js";
import * as ui from "./ui.js";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface ApiTargets {
  apiBaseUrl: string;
  inferenceBaseUrl: string;
}

export interface WizardAccount {
  apiKey: string;
  organizationName: string;
  balanceNanoUsd: number;
}

export const resolveAccount = async (
  targets: ApiTargets,
  choice: "signup" | "login",
): Promise<WizardAccount> => {
  return exchange(targets, choice);
};

const exchange = async (
  targets: ApiTargets,
  choice: "signup" | "login",
): Promise<WizardAccount> => {
  const email = await ui.askText("Email:", (value) => {
    const trimmed = value.trim();
    if (!EMAIL_PATTERN.test(trimmed)) return "Enter a valid email address.";
    return undefined;
  });

  const send = ui.spinner();
  send.start("Requesting a verification code");
  try {
    await request(
      `${targets.apiBaseUrl.replace(/\/$/, "")}/api/auth/email-otp/send-verification-otp`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim(), type: "sign-in" }),
        redirect: "error",
      },
    );
  } catch (error) {
    send.stop("Could not send the code", 1);
    throw error;
  }
  send.stop("Code sent");

  ui.note(
    `Check ${email.trim()} for a six-digit code. It expires in 10 minutes.`,
    "Email sent",
  );

  const code = await ui.askText("Code:", (value) =>
    /^\d{6}$/.test(value.trim()) ? undefined : "Enter the six-digit code.",
  );

  let sessionCookie = "";
  const session = ui.spinner();
  session.start("Verifying the code");
  try {
    const response = await request(
      `${targets.apiBaseUrl.replace(/\/$/, "")}/api/auth/sign-in/email-otp`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim(), otp: code.trim() }),
        redirect: "error",
      },
    );
    // Node fetch has no cookie jar. Keep the session in memory and forward
    // only name/value pairs to key creation on this same API.
    // Older Node 18 releases expose multiple cookies as a combined header.
    const cookies =
      typeof response.headers.getSetCookie === "function"
        ? response.headers.getSetCookie()
        : (response.headers.get("set-cookie") ?? "").split(
            /,(?=\s*[^;,=\s]+=)/,
          );
    sessionCookie = cookies
      .map((cookie) => cookie.split(";")[0]?.trim())
      .filter(Boolean)
      .join("; ");
    if (!sessionCookie) {
      throw new Error(
        "Sign-in did not return a session cookie. Run the wizard again.",
      );
    }
  } catch (error) {
    session.stop("Verification failed", 1);
    if (
      error instanceof HttpError &&
      (error.status === 400 || error.status === 401 || error.status === 422)
    ) {
      ui.fail("The code was rejected. Run the wizard and request a new one.");
    }
    throw error;
  }
  session.stop("Verified");

  const mint = ui.spinner();
  mint.start("Creating your local API key");
  let body: {
    secret?: unknown;
    organization_name?: unknown;
    balance_nano_usd?: unknown;
  };
  try {
    const response = await request(
      `${targets.apiBaseUrl.replace(/\/$/, "")}/api/v1/wizard/key`,
      {
        method: "POST",
        headers: { cookie: sessionCookie },
        redirect: "error",
      },
    );
    body = response.body as typeof body;
  } catch (error) {
    mint.stop("Key creation failed", 1);
    throw error;
  }
  mint.stop("Key created");

  if (typeof body.secret !== "string" || body.secret.length === 0) {
    throw new HttpError(
      0,
      "invalid_response",
      "The key response did not include a secret.",
    );
  }

  const balance =
    typeof body.balance_nano_usd === "number" ? body.balance_nano_usd : 0;
  if (balance > 0) {
    ui.success("Account created. Free credit applied.");
    ui.info(
      `Current balance: $${(balance / 1_000_000_000).toFixed(2)} (from the API).`,
    );
  } else if (choice === "login") {
    ui.success("Logged in.");
  }

  return {
    apiKey: body.secret,
    organizationName:
      typeof body.organization_name === "string" ? body.organization_name : "",
    balanceNanoUsd: balance,
  };
};
