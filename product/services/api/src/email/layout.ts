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
