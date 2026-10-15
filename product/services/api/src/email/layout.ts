export interface EmailContent {
  html: string;
  text: string;
}

interface EmailShellContent {
  body: string;
  eyebrow?: string;
  preheader: string;
  title: string;
}

const htmlEntities: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>"']/g,
    (character) => htmlEntities[character] ?? character,
  );

export const emailParagraph = (html: string, margin = "0 0 20px"): string =>
  `<p style="margin:${margin};font-family:Arial,sans-serif;font-size:16px;line-height:1.65;color:#444444;">${html}</p>`;

export const emailNote = (html: string, margin = "0 0 12px"): string =>
  `<p style="margin:${margin};font-family:Arial,sans-serif;font-size:13px;line-height:1.6;color:#444444;">${html}</p>`;

export const emailButton = (safeUrl: string, label: string): string =>
  `<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;">
                  <tr>
                    <td bgcolor="#000000" style="background-color:#000000;border-radius:12px;">
                      <a href="${safeUrl}" style="display:inline-block;padding:15px 24px;font-family:Arial,sans-serif;font-size:12px;font-weight:700;line-height:1;letter-spacing:0.8px;text-transform:uppercase;text-decoration:none;color:#ffffff;border-radius:12px;">${label}</a>
                    </td>
                  </tr>
                </table>`;

export const emailLinkFallback = (safeUrl: string): string =>
  `${emailNote("If the button does not work, copy and paste this link into your browser:")}
                  <p style="margin:0;font-family:Arial,sans-serif;font-size:12px;line-height:1.6;word-break:break-all;"><a href="${safeUrl}" style="color:#000000;text-decoration:underline;">${safeUrl}</a></p>`;

export const createEmailShell = ({
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
