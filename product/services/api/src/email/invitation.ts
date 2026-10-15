import type { OrganizationRole } from "@gradiated/contracts";

import {
  createEmailShell,
  emailButton,
  emailLinkFallback,
  emailNote,
  emailParagraph,
  escapeHtml,
  type EmailContent,
} from "./layout.js";
import { sendResendEmail, type ResendConfiguration } from "./resend.js";

export interface InvitationMessage {
  email: string;
  invitedByEmail: string;
  organizationName: string;
  role: OrganizationRole;
  url: string;
}

export type InvitationSender = (message: InvitationMessage) => Promise<void>;

export const invitationUrl = (consoleUrl: string, token: string): string => {
  const url = new URL("/invitations/accept", consoleUrl);
  url.searchParams.set("token", token);

  return url.toString();
};

const invitationSubject = ({
  invitedByEmail,
  organizationName,
}: InvitationMessage): string =>
  `${invitedByEmail} invited you to ${organizationName} on Gradiated`;

const createInvitationEmailContent = (
  message: InvitationMessage,
): EmailContent => {
  const inviter = escapeHtml(message.invitedByEmail);
  const organization = escapeHtml(message.organizationName);
  const email = escapeHtml(message.email);
  const url = escapeHtml(message.url);
  const role = message.role === "admin" ? "an admin" : "a member";

  return {
    html: createEmailShell({
      title: `Join ${message.organizationName} on Gradiated`,
      preheader: `${message.invitedByEmail} invited you to join ${message.organizationName} on Gradiated.`,
      body: `${emailParagraph(`<strong style="color:#000000;">${inviter}</strong> invited you to join <strong style="color:#000000;">${organization}</strong> on Gradiated as ${role}.`)}
                ${emailParagraph(`Gradiated serves open-weight models through an OpenAI-compatible API. Accept to use ${organization}'s workspaces, API keys and usage.`, "0 0 30px")}
                ${emailButton(url, "Accept invitation")}
                <div style="margin:36px 0 0;padding:24px 0 0;border-top:1px solid #d5ccbb;">
                  ${emailNote(`This invitation is for ${email} and expires in 7 days.`)}
                  ${emailLinkFallback(url)}
                  ${emailNote("If you weren't expecting this, you can ignore it.", "20px 0 0")}
                </div>`,
    }),
    text: `Join ${message.organizationName} on Gradiated\n\n${message.invitedByEmail} invited you to join ${message.organizationName} on Gradiated as ${role}.\n\nAccept the invitation:\n${message.url}\n\nThis invitation is for ${message.email} and expires in 7 days.\n\nIf you weren't expecting this, you can ignore it.`,
  };
};

export const createResendInvitationSender =
  (configuration: ResendConfiguration): InvitationSender =>
  (message) =>
    sendResendEmail(configuration, {
      to: message.email,
      subject: invitationSubject(message),
      content: createInvitationEmailContent(message),
    });
