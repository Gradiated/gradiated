import { SendEmailCommand, SESv2Client } from "@aws-sdk/client-sesv2";

export interface MagicLinkMessage {
  email: string;
  url: string;
}

export type MagicLinkSender = (message: MagicLinkMessage) => Promise<void>;

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

export const createMagicLinkEmailContent = (
  url: string,
): { html: string; text: string } => ({
  html: `<!doctype html><html><body><p><a href="${escapeHtml(url)}">Sign in to Gradiated</a></p><p>This link expires in 10 minutes and can be used once.</p><p>If you did not request it, you can ignore this email.</p></body></html>`,
  text: `${url}\n\nThis link expires in 10 minutes and can be used once.\n\nIf you did not request it, you can ignore this email.`,
});

export const createSesMagicLinkSender = (configuration: {
  from: string;
  region: string;
}): MagicLinkSender => {
  const client = new SESv2Client({ region: configuration.region });

  return async ({ email, url }) => {
    const content = createMagicLinkEmailContent(url);
    await client.send(
      new SendEmailCommand({
        FromEmailAddress: configuration.from,
        Destination: { ToAddresses: [email] },
        Content: {
          Simple: {
            Subject: { Charset: "UTF-8", Data: "Sign in to Gradiated" },
            Body: {
              Text: {
                Charset: "UTF-8",
                Data: content.text,
              },
              Html: {
                Charset: "UTF-8",
                Data: content.html,
              },
            },
          },
        },
      }),
    );
  };
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

export const createSesOtpSender = (configuration: {
  from: string;
  region: string;
}): OtpCodeSender => {
  const client = new SESv2Client({ region: configuration.region });

  return async ({ code, email }) => {
    const safeCode = escapeHtml(code);
    await client.send(
      new SendEmailCommand({
        FromEmailAddress: configuration.from,
        Destination: { ToAddresses: [email] },
        Content: {
          Simple: {
            Subject: {
              Charset: "UTF-8",
              Data: "Your Gradiated verification code",
            },
            Body: {
              Text: {
                Charset: "UTF-8",
                Data: `Your Gradiated verification code:\n\n${code}\n\nThis code expires shortly and can be used once. If you did not request it, you can ignore this email.`,
              },
              Html: {
                Charset: "UTF-8",
                Data: `<!doctype html><html><body><p>Your Gradiated verification code:</p><p><strong>${safeCode}</strong></p><p>This code expires shortly and can be used once.</p></body></html>`,
              },
            },
          },
        },
      }),
    );
  };
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
