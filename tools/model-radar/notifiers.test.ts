import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { Alert } from "./model.ts";
import { ConsoleNotifier, SlackNotifier } from "./notifiers.ts";
import { fakeFetch } from "./fakes.ts";

const WEBHOOK = "https://hooks.slack.test/services/secret";

const openRouter: Alert = {
  source: "OpenRouter",
  lab: "Moonshot AI",
  models: [
    {
      id: "moonshotai/kimi-k3.1-pro",
      owner: "moonshotai",
      name: "MoonshotAI: Kimi K3.1 Pro",
      url: "https://openrouter.ai/moonshotai/kimi-k3.1-pro",
      details: ["served by Moonshot AI and 16 others", "weights live"],
    },
  ],
};

const hub: Alert = {
  source: "Hugging Face",
  lab: "R&D <Lab>",
  models: ["a", "b"].map((name) => ({
    id: `lab/${name}`,
    owner: "lab",
    name: `lab/${name}`,
    url: `https://huggingface.co/lab/${name}`,
    details: [],
  })),
};

describe("SlackNotifier", () => {
  it("formats a linked line per model", () => {
    assert.equal(
      SlackNotifier.format(openRouter),
      [
        "*🛰️ OpenRouter · Moonshot AI: new model*",
        "• <https://openrouter.ai/moonshotai/kimi-k3.1-pro|MoonshotAI: Kimi K3.1 Pro> `moonshotai/kimi-k3.1-pro` · served by Moonshot AI and 16 others · weights live",
      ].join("\n"),
    );
  });

  it("escapes Slack markup", () => {
    assert.equal(
      SlackNotifier.format(hub),
      [
        "*🤗 Hugging Face · R&amp;D &lt;Lab&gt;*",
        "• <https://huggingface.co/lab/a|lab/a>",
        "• <https://huggingface.co/lab/b|lab/b>",
      ].join("\n"),
    );
  });

  it("posts one message per alert to the webhook", async () => {
    const { send, calls } = fakeFetch({ [WEBHOOK]: () => new Response("ok") });
    await new SlackNotifier(send, WEBHOOK).send([openRouter, hub]);

    assert.equal(calls.length, 2);
    assert.equal(calls[0]!.url, WEBHOOK);
    assert.equal(calls[0]!.init?.method, "POST");
    assert.deepEqual(JSON.parse(String(calls[0]!.init?.body)), {
      text: SlackNotifier.format(openRouter),
      unfurl_links: false,
    });
  });

  it("fails without putting the webhook in the error", async () => {
    const { send } = fakeFetch({
      [WEBHOOK]: () => new Response("no", { status: 403 }),
    });
    await assert.rejects(
      new SlackNotifier(send, WEBHOOK).send([hub]),
      (error: Error) => {
        assert.match(error.message, /Slack webhook failed \(HTTP 403\)/);
        assert.doesNotMatch(error.message, /secret/);
        return true;
      },
    );
  });
});

describe("ConsoleNotifier", () => {
  it("prints each alert as plain text", async () => {
    const lines: string[] = [];
    await new ConsoleNotifier((line) => lines.push(line)).send([openRouter]);
    assert.deepEqual(lines, [
      [
        "🛰️ OpenRouter · Moonshot AI: new model",
        "  • MoonshotAI: Kimi K3.1 Pro (moonshotai/kimi-k3.1-pro) · served by Moonshot AI and 16 others · weights live https://openrouter.ai/moonshotai/kimi-k3.1-pro",
      ].join("\n"),
    ]);
  });
});
