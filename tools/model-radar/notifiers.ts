// Where alerts go. Each channel is one class implementing Notifier, so a new
// one (another Slack channel, email, Discord) is a new class, nothing else.

import type { Alert, Model, Notifier, SourceName } from "./model.ts";

const ICON: Record<SourceName, string> = {
  "Hugging Face": "🤗",
  OpenRouter: "🛰️",
};

/** "🤗 Hugging Face · Moonshot AI", or "🛰️ OpenRouter · Tencent: new model". */
const headline = ({ source, lab, models }: Alert) => {
  const title = `${ICON[source]} ${source} · ${lab}`;
  if (source === "Hugging Face") return title;
  const what =
    models.length === 1 ? "new model" : `${models.length} new models`;
  return `${title}: ${what}`;
};

/** Posts one message per alert to a Slack incoming webhook. */
export class SlackNotifier implements Notifier {
  readonly #fetch: typeof fetch;
  readonly #webhook: string;

  constructor(send: typeof fetch, webhook: string) {
    this.#fetch = send;
    this.#webhook = webhook;
  }

  async send(alerts: Alert[]): Promise<void> {
    for (const alert of alerts) {
      const response = await this.#fetch(this.#webhook, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          text: SlackNotifier.format(alert),
          unfurl_links: false,
        }),
        signal: AbortSignal.timeout(15_000),
      });
      // Never include the webhook URL in errors or logs: it is the secret.
      if (!response.ok)
        throw new Error(`Slack webhook failed (HTTP ${response.status}).`);
    }
  }

  /** Slack mrkdwn: a bold headline, then one linked line per model. */
  static format(alert: Alert): string {
    const lines = alert.models.map((model) => {
      const link = `<${model.url}|${escapeSlack(model.name)}>`;
      const id = model.name === model.id ? "" : ` \`${escapeSlack(model.id)}\``;
      return `• ${link}${id}${detailsText(model, escapeSlack)}`;
    });
    return [`*${escapeSlack(headline(alert))}*`, ...lines].join("\n");
  }
}

/** Prints alerts instead of sending them: the dry run. */
export class ConsoleNotifier implements Notifier {
  readonly #print: (line: string) => void;

  constructor(print: (line: string) => void) {
    this.#print = print;
  }

  async send(alerts: Alert[]): Promise<void> {
    for (const alert of alerts) this.#print(ConsoleNotifier.format(alert));
  }

  static format(alert: Alert): string {
    const lines = alert.models.map((model) => {
      const id = model.name === model.id ? "" : ` (${model.id})`;
      return `  • ${model.name}${id}${detailsText(model, (text) => text)} ${model.url}`;
    });
    return [headline(alert), ...lines].join("\n");
  }
}

/** " · weights live · served by Tencent", or "" when there are no details. */
const detailsText = (model: Model, clean: (text: string) => string) =>
  model.details.length ? ` · ${model.details.map(clean).join(" · ")}` : "";

/** Slack treats &, < and > as markup; everything else is literal. */
const escapeSlack = (text: string) =>
  text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
