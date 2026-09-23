import { serviceLog } from "../logging.js";
import { createEmailShell, escapeHtml, type EmailContent } from "./layout.js";
import { sendResendEmail, type ResendConfiguration } from "./resend.js";

export interface WaitlistWelcomeMessage {
  email: string;
}

export type WaitlistWelcomeSender = (
  message: WaitlistWelcomeMessage,
) => Promise<void>;

const welcomeContent = (): EmailContent => {
  const body = [
    "Thanks for joining the Gradiated waitlist — you're on the list for the beta.",
    "We are onboarding teams in small groups so every workload gets real attention. When a spot opens, the invitation comes to this address.",
    "If anything changes about your inference plans in the meantime, just reply to this email — it reaches people, not a queue.",
  ];

  return {
    html: createEmailShell({
      eyebrow: "Waitlist",
      title: "You're on the list.",
      preheader: "Thanks for signing up — your beta invitation will land here.",
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
  (configuration: ResendConfiguration): WaitlistWelcomeSender =>
  ({ email }) =>
    sendResendEmail(configuration, {
      to: email,
      subject: "You're on the Gradiated waitlist",
      content: welcomeContent(),
    });

export const createLoggingWaitlistWelcomeSender =
  (): WaitlistWelcomeSender => async () => {
    serviceLog("info", "waitlist_welcome_skipped");
  };
