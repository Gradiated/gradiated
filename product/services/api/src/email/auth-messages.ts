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

export interface MagicLinkMessage {
  email: string;
  url: string;
}

export type MagicLinkSender = (message: MagicLinkMessage) => Promise<void>;

export interface OtpCodeMessage {
  code: string;
  email: string;
}

export type OtpCodeSender = (message: OtpCodeMessage) => Promise<void>;

export const createMagicLinkEmailContent = (url: string): EmailContent => {
  const safeUrl = escapeHtml(url);
  return {
    html: createEmailShell({
      body: `${emailParagraph("Use the button below to securely sign in to your account.", "0 0 30px")}
                ${emailButton(safeUrl, "Sign in")}
                <div style="margin:36px 0 0;padding:24px 0 0;border-top:1px solid #d5ccbb;">
                  ${emailNote("This link expires in 10 minutes and can be used once.")}
                  ${emailLinkFallback(safeUrl)}
                  ${emailNote("If you did not request this email, you can ignore it.", "20px 0 0")}
                </div>`,
      preheader: "Use this secure link to sign in to Gradiated.",
      title: "Sign in to Gradiated",
    }),
    text: `Sign in to Gradiated\n\nUse this link to sign in:\n${url}\n\nThis link expires in 10 minutes and can be used once.\n\nIf you did not request this email, you can ignore it.`,
  };
};

export const createOtpCodeEmailContent = (code: string): EmailContent => ({
  html: createEmailShell({
    body: `<p style="margin:0 0 26px;font-family:Arial,sans-serif;font-size:16px;line-height:1.65;color:#444444;">Enter this code to continue to Gradiated.</p>
                <div class="email-code" style="margin:0;padding:22px 16px 22px 24px;border:1px solid #d5ccbb;background-color:#efece3;font-family:'Courier New',monospace;font-size:32px;font-weight:700;line-height:1;letter-spacing:8px;text-align:center;color:#000000;">${escapeHtml(code)}</div>
                <div style="margin:36px 0 0;padding:24px 0 0;border-top:1px solid #d5ccbb;">
                  <p style="margin:0;font-family:Arial,sans-serif;font-size:13px;line-height:1.6;color:#444444;">This code expires in 10 minutes and can be used once.</p>
                  <p style="margin:20px 0 0;font-family:Arial,sans-serif;font-size:13px;line-height:1.6;color:#444444;">If you did not request this email, you can ignore it.</p>
                </div>`,
    eyebrow: "Verification code",
    preheader: `Your Gradiated verification code is ${code}.`,
    title: "Your verification code",
  }),
  text: `Your Gradiated verification code\n\n${code}\n\nThis code expires in 10 minutes and can be used once.\n\nIf you did not request this email, you can ignore it.`,
});

export const createResendMagicLinkSender =
  (configuration: ResendConfiguration): MagicLinkSender =>
  ({ email, url }) =>
    sendResendEmail(configuration, {
      to: email,
      subject: "Sign in to Gradiated",
      content: createMagicLinkEmailContent(url),
    });

export const createResendOtpSender =
  (configuration: ResendConfiguration): OtpCodeSender =>
  ({ code, email }) =>
    sendResendEmail(configuration, {
      to: email,
      subject: "Your Gradiated verification code",
      content: createOtpCodeEmailContent(code),
    });
