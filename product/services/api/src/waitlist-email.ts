import {
  createEmailShell,
  sendResendEmail,
  type ResendConfiguration,
} from "./auth-email.js";

export interface WaitlistWelcomeMessage {
  email: string;
}

export type WaitlistWelcomeSender = (
  message: WaitlistWelcomeMessage,
) => Promise<void>;

/** The same branded shell the auth emails use, so the first thing a signup
 *  receives from us looks like the site they just left. */
const welcomeContent = () => {
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
      body: body.map((line) => `<p>${line}</p>`).join("\n"),
    }),
    text: `You're on the list.\n\n${body.join("\n\n")}\n\n— Gradiated`,
  };
};

export const createResendWaitlistWelcomeSender =
  (configuration: ResendConfiguration): WaitlistWelcomeSender =>
  async ({ email }) => {
    await sendResendEmail(
      configuration,
      email,
      "You're on the Gradiated waitlist",
      welcomeContent(),
    );
  };

/** Used when no email credentials are configured (local dev, tests): the
 *  signup still succeeds, the send is a log line instead of a failure. */
export const createLoggingWaitlistWelcomeSender =
  (log: (message: string) => void = console.log): WaitlistWelcomeSender =>
  async ({ email }) => {
    log(`[waitlist] welcome email suppressed (no email transport): ${email}`);
  };
