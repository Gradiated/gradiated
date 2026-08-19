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

export const createSesMagicLinkSender = (configuration: {
  from: string;
  region: string;
}): MagicLinkSender => {
  const client = new SESv2Client({ region: configuration.region });

  return async ({ email, url }) => {
    const safeUrl = escapeHtml(url);
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
                Data: `Sign in to Gradiated:\n\n${url}\n\nThis link expires in 10 minutes and can be used once. If you did not request it, you can ignore this email.`,
              },
              Html: {
                Charset: "UTF-8",
                Data: `<!doctype html><html><body><p>Sign in to Gradiated.</p><p><a href="${safeUrl}">Sign in to Gradiated</a></p><p>This link expires in 10 minutes and can be used once.</p><p>If you did not request it, you can ignore this email.</p></body></html>`,
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
