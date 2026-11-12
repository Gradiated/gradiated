import type { ContactChannel } from "@gradiated/contracts";

import { serviceLog } from "../logging.js";
import {
  createEmailShell,
  emailParagraph,
  escapeHtml,
  type EmailContent,
} from "./layout.js";
import { sendResendEmail, type ResendConfiguration } from "./resend.js";

export interface EngineerOnboardingNotice {
  organizationId: string;
  organizationName: string;
  submittedByEmail: string;
  contactChannel: ContactChannel;
  githubAccounts: string[];
  slackChannel: string | null;
  ndaSignedAt: string | null;
  notes: string | null;
}

export type EngineerOnboardingNotifier = (
  notice: EngineerOnboardingNotice,
) => Promise<void>;

const noticeLines = (notice: EngineerOnboardingNotice): [string, string][] => [
  ["Organization", `${notice.organizationName} (${notice.organizationId})`],
  ["Submitted by", notice.submittedByEmail],
  ["Preferred contact", notice.contactChannel],
  ["GitHub", notice.githubAccounts.join(", ") || "None"],
  ["Slack channel", notice.slackChannel ?? "None"],
  [
    "Mutual NDA",
    notice.ndaSignedAt ? `Signed ${notice.ndaSignedAt}` : "Not requested",
  ],
];

const noticeContent = (notice: EngineerOnboardingNotice): EmailContent => {
  const lines = noticeLines(notice);
  const notes = notice.notes ?? "No notes.";

  return {
    html: createEmailShell({
      eyebrow: "Engineer onboarding",
      title: `${notice.organizationName} is ready to start`,
      preheader: `${notice.submittedByEmail} finished engineer onboarding.`,
      body: [
        ...lines.map(([label, value]) =>
          emailParagraph(
            `<strong style="color:#000000;">${escapeHtml(label)}:</strong> ${escapeHtml(value)}`,
            "0 0 8px",
          ),
        ),
        emailParagraph(escapeHtml(notes).replaceAll("\n", "<br>"), "24px 0 0"),
      ].join("\n"),
    }),
    text: `${lines.map(([label, value]) => `${label}: ${value}`).join("\n")}\n\n${notes}`,
  };
};

export const ENGINEER_ONBOARDING_EMAIL = "team@gradiated.com";

export const createResendEngineerOnboardingNotifier =
  (configuration: ResendConfiguration): EngineerOnboardingNotifier =>
  (notice) =>
    sendResendEmail(configuration, {
      to: ENGINEER_ONBOARDING_EMAIL,
      subject: `Engineer onboarding submitted: ${notice.organizationName}`,
      content: noticeContent(notice),
    });

export const createLoggingEngineerOnboardingNotifier =
  (): EngineerOnboardingNotifier => async (notice) => {
    serviceLog("warn", "engineer_onboarding_notification_skipped", {
      organization_id: notice.organizationId,
      reason: "test_mail",
    });
  };
