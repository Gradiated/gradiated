export interface MagicLinkMessage {
  email: string;
  url: string;
}

export type MagicLinkSender = (message: MagicLinkMessage) => Promise<void>;

interface EmailContent {
  html: string;
  text: string;
}

interface EmailShellContent {
  body: string;
  eyebrow?: string;
  preheader: string;
  title: string;
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character]!,
  );

const createEmailShell = ({
  body,
  eyebrow,
  preheader,
  title,
}: EmailShellContent): string => `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <meta name="supported-color-schemes" content="light">
    <title>${escapeHtml(title)}</title>
    <style>
      @media only screen and (max-width: 480px) {
        .email-card { padding: 36px 24px 32px !important; }
        .email-title { font-size: 34px !important; letter-spacing: -1.2px !important; }
        .email-code { padding-right: 11px !important; padding-left: 16px !important; font-size: 28px !important; letter-spacing: 5px !important; }
      }
    </style>
  </head>
  <body style="margin:0;padding:0;background-color:#efece3;color:#000000;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">${escapeHtml(preheader)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#efece3" style="width:100%;background-color:#efece3;border-collapse:collapse;">
      <tr>
        <td align="center" style="padding:48px 16px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;border-collapse:separate;border-spacing:0;">
            <tr>
              <td style="padding:0 0 24px;font-family:Georgia,'Times New Roman',serif;font-size:24px;font-weight:600;line-height:1;letter-spacing:-1.2px;color:#000000;">
                <img src="https://gradiated.com/brand/png/gradiated-mark-dark-180.png" width="36" height="36" alt="" style="display:inline-block;border:0;vertical-align:middle;margin-right:10px;"> <span style="vertical-align:middle;font-family:Arial,Helvetica,sans-serif;">Gradiated</span>
              </td>
            </tr>
            <tr>
              <td class="email-card" bgcolor="#f6f3ec" style="border:1px solid #d5ccbb;border-radius:12px;background-color:#f6f3ec;padding:48px 48px 44px;">
                ${eyebrow ? `<p style="margin:0 0 18px;font-family:Arial,sans-serif;font-size:11px;font-weight:700;line-height:1.3;letter-spacing:1.2px;text-transform:uppercase;color:#5e6043;">${escapeHtml(eyebrow)}</p>` : ""}
                <h1 class="email-title" style="margin:0 0 24px;font-family:Georgia,'Times New Roman',serif;font-size:40px;font-weight:400;line-height:1.05;letter-spacing:-1.6px;color:#000000;">${escapeHtml(title)}</h1>
                ${body}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>`;

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

interface ResendConfiguration {
  from: string;
  apiKey: string;
  fetch?: typeof globalThis.fetch;
}

const sendResendEmail = async (
  configuration: ResendConfiguration,
  email: string,
  subject: string,
  content: EmailContent,
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
          to: [email],
          subject,
          ...content,
        }),
        signal: AbortSignal.timeout(10_000),
      },
    );
  } catch {
    // Never attach provider errors that could contain credentials or email content.
    throw new Error("Email delivery request failed.");
  }
  if (!response.ok) {
    throw new Error(`Email delivery failed (Resend HTTP ${response.status}).`);
  }
};

export const createResendMagicLinkSender =
  (configuration: ResendConfiguration): MagicLinkSender =>
  async ({ email, url }) => {
    await sendResendEmail(
      configuration,
      email,
      "Sign in to Gradiated",
      createMagicLinkEmailContent(url),
    );
  };

export interface TestMagicLinkTransport {
  send: MagicLinkSender;
  take(email: string): string | null;
}

export const createTestMagicLinkTransport = (): TestMagicLinkTransport => {
  const links = new Map<string, string>();
  return {
    send: async ({ email, url }) => {
      links.set(email.trim().toLowerCase(), url);
    },
    take: (email) => {
      const key = email.trim().toLowerCase();
      const url = links.get(key) ?? null;
      links.delete(key);
      return url;
    },
  };
};

export interface OtpCodeMessage {
  code: string;
  email: string;
}

export type OtpCodeSender = (message: OtpCodeMessage) => Promise<void>;

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

export const createResendOtpSender =
  (configuration: ResendConfiguration): OtpCodeSender =>
  async ({ code, email }) => {
    await sendResendEmail(
      configuration,
      email,
      "Your Gradiated verification code",
      createOtpCodeEmailContent(code),
    );
  };

export interface TestOtpTransport {
  send: OtpCodeSender;
  take(email: string): string | null;
}

export const createTestOtpTransport = (): TestOtpTransport => {
  const codes = new Map<string, string>();
  return {
    send: async ({ code, email }) => {
      codes.set(email.trim().toLowerCase(), code);
    },
    take: (email) => {
      const key = email.trim().toLowerCase();
      const code = codes.get(key) ?? null;
      codes.delete(key);
      return code;
    },
  };
};
