import { serviceLog } from "../logging.js";
import { createEmailShell, escapeHtml, type EmailContent } from "./layout.js";
import { sendResendEmail, type ResendConfiguration } from "./resend.js";

export interface WaitlistWelcomeMessage {
  email: string;
}

export type WaitlistWelcomeSender = (
  message: WaitlistWelcomeMessage,
) => Promise<void>;

const welcomeContent = (consoleUrl: string): EmailContent => {
  const body = [
    "Thanks for joining the Gradiated post-training waitlist — you're on the list for the private beta.",
    "Post-training is not yet available for self serve. When access is available, we will contact you at this address.",
    `You can already sign in and use hosted inference at ${consoleUrl}. If your post-training plans change, just reply to this email.`,
  ];

  return {
    html: createEmailShell({
      eyebrow: "Waitlist",
      title: "You're on the list.",
      preheader:
        "Thanks for signing up — we will contact you about post-training access.",
      body: body
        .map(
          (line) =>
            `<p style="margin:0 0 20px;font-family:Arial,sans-serif;font-size:16px;line-height:1.65;color:#444444;">${escapeHtml(line)}</p>`,
        )
        .join("\n"),
    }),
    text: `You're on the list.\n\n${body.join("\n\n")}\n\n— Gradiated`,
  };
};

export const createResendWaitlistWelcomeSender =
  (
    configuration: ResendConfiguration & { consoleUrl: string },
  ): WaitlistWelcomeSender =>
  ({ email }) =>
    sendResendEmail(configuration, {
      to: email,
      subject: "You're on the Gradiated post-training waitlist",
      content: welcomeContent(configuration.consoleUrl),
    });

export const createLoggingWaitlistWelcomeSender =
  (): WaitlistWelcomeSender => async () => {
    serviceLog("info", "waitlist_welcome_skipped");
  };
