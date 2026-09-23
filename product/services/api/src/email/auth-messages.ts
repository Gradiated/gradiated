import { createEmailShell, escapeHtml, type EmailContent } from "./layout.js";
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
      body: `<p style="margin:0 0 30px;font-family:Arial,sans-serif;font-size:16px;line-height:1.65;color:#444444;">Use the button below to securely sign in to your account.</p>
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;">
                  <tr>
                    <td bgcolor="#000000" style="background-color:#000000;border-radius:12px;">
                      <a href="${safeUrl}" style="display:inline-block;padding:15px 24px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;line-height:1;letter-spacing:0.8px;text-transform:uppercase;text-decoration:none;color:#ffffff;border-radius:12px;">Sign in</a>
                    </td>
                  </tr>
                </table>
                <div style="margin:36px 0 0;padding:24px 0 0;border-top:1px solid #d5ccbb;">
                  <p style="margin:0 0 12px;font-family:Arial,sans-serif;font-size:13px;line-height:1.6;color:#444444;">This link expires in 10 minutes and can be used once.</p>
                  <p style="margin:0 0 12px;font-family:Arial,sans-serif;font-size:13px;line-height:1.6;color:#444444;">If the button does not work, copy and paste this link into your browser:</p>
                  <p style="margin:0;font-family:Arial,sans-serif;font-size:12px;line-height:1.6;word-break:break-all;"><a href="${safeUrl}" style="color:#000000;text-decoration:underline;">${safeUrl}</a></p>
                  <p style="margin:20px 0 0;font-family:Arial,sans-serif;font-size:13px;line-height:1.6;color:#444444;">If you did not request this email, you can ignore it.</p>
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
