import type { EmailContent } from "./layout.js";

export interface ResendConfiguration {
  from: string;
  apiKey: string;
  fetch?: typeof globalThis.fetch;
}

export class EmailDeliveryError extends Error {
  constructor(
    readonly code: `${number}` | "ETIMEDOUT" | "ENETWORK",
    message: string,
  ) {
    super(message);
    this.name = "EmailDeliveryError";
  }
}

export const sendResendEmail = async (
  configuration: ResendConfiguration,
  {
    to,
    subject,
    content,
  }: { to: string; subject: string; content: EmailContent },
): Promise<void> => {
  let response: Response;
  try {
    response = await (configuration.fetch ?? globalThis.fetch)(
      "https://api.resend.com/emails",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${configuration.apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: configuration.from,
          to: [to],
          subject,
          ...content,
        }),
        signal: AbortSignal.timeout(10_000),
      },
    );
  } catch (error) {
    // Never attach provider errors that could contain credentials or email content.
    if (error instanceof Error && error.name === "TimeoutError") {
      throw new EmailDeliveryError("ETIMEDOUT", "Email delivery timed out.");
    }
    throw new EmailDeliveryError("ENETWORK", "Email delivery request failed.");
  }

  if (!response.ok) {
    throw new EmailDeliveryError(
      `${response.status}`,
      `Email delivery failed (Resend HTTP ${response.status}).`,
    );
  }
};
