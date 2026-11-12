import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";
import { Radar } from "./radar.ts";
import { SeenStore } from "./seen-store.ts";
import { FakeSource, RecordingNotifier, model } from "./testing.ts";
import { Watchlist } from "./watchlist.ts";

const dir = await mkdtemp(join(tmpdir(), "model-radar-"));
after(() => rm(dir, { recursive: true, force: true }));

const watchlist = Watchlist.parse([
  { lab: "Qwen", huggingface: ["Qwen"], openrouter: ["qwen"] },
  { lab: "Google Gemma", huggingface: ["google"], include: ["gemma"] },
]);

let runs = 0;
/** A radar over two fake sources, with its own empty seen-IDs file. */
const setup = () => {
  const hub = new FakeSource("Hugging Face");
  const router = new FakeSource("OpenRouter");
  const notifier = new RecordingNotifier();
  const store = new SeenStore(join(dir, `seen-${++runs}.json`));
  const log: string[] = [];
  const radar = (save = true) =>
    new Radar({
      sources: [hub, router],
      watchlist,
      store,
      notifiers: [notifier],
      log: (l) => log.push(l),
      save,
    });
  return { hub, router, notifier, store, log, radar };
};

const qwen = (...ids: string[]) => ({
  scope: "huggingface:Qwen",
  owner: "Qwen",
  models: ids.map((id) => model(`Qwen/${id}`)),
});

describe("Radar", () => {
  it("records everything silently on the first run", async () => {
    const { hub, notifier, store, log, radar } = setup();
    hub.next = [qwen("A", "B")];

    const { alerts } = await radar().run();

    assert.deepEqual(alerts, []);
    assert.deepEqual(notifier.sent, []);
    assert.deepEqual(await store.load(), {
      "huggingface:Qwen": ["Qwen/A", "Qwen/B"],
    });
    assert.ok(
      log.some((line) =>
        line.includes(
          "started watching huggingface:Qwen (2 models, no alerts)",
        ),
      ),
    );
  });

  it("alerts on models not seen before, grouped by source and lab", async () => {
    const { hub, router, notifier, radar } = setup();
    hub.next = [qwen("A")];
    router.next = [{ scope: "openrouter:qwen", owner: "qwen", models: [] }];
    await radar().run();

    hub.next = [qwen("A", "B", "C")];
    router.next = [
      {
        scope: "openrouter:qwen",
        owner: "qwen",
        models: [model("qwen/qwen-x")],
      },
    ];
    const { alerts } = await radar().run();

    const expected = [
      {
        source: "Hugging Face",
        lab: "Qwen",
        models: [model("Qwen/B"), model("Qwen/C")],
      },
      { source: "OpenRouter", lab: "Qwen", models: [model("qwen/qwen-x")] },
    ];
    assert.deepEqual(alerts, expected);
    assert.deepEqual(notifier.sent, [expected]);
  });

  it("does not alert again for a model that disappears and comes back", async () => {
    const { hub, radar } = setup();
    hub.next = [qwen("A")];
    await radar().run();
    hub.next = [qwen()];
    await radar().run();
    hub.next = [qwen("A")];
    assert.deepEqual((await radar().run()).alerts, []);
  });

  it("only alerts on models that match the lab's filter", async () => {
    const { hub, radar } = setup();
    const google = (...ids: string[]) => ({
      scope: "huggingface:google",
      owner: "google",
      models: ids.map((id) => model(`google/${id}`)),
    });
    hub.next = [google()];
    await radar().run();
    hub.next = [google("gemma-4-31b", "t5-xxl")];

    const { alerts } = await radar().run();

    assert.deepEqual(alerts, [
      {
        source: "Hugging Face",
        lab: "Google Gemma",
        models: [model("google/gemma-4-31b")],
      },
    ]);
  });

  it("keeps a failed source's IDs and still runs the others", async () => {
    const { hub, router, store, radar } = setup();
    hub.next = [qwen("A")];
    router.next = [{ scope: "openrouter:qwen", owner: "qwen", models: [] }];
    await radar().run();

    hub.next = new Error("Hugging Face is down");
    router.next = [
      {
        scope: "openrouter:qwen",
        owner: "qwen",
        models: [model("qwen/qwen-x")],
      },
    ];
    const { alerts, failures } = await radar().run();

    assert.deepEqual(
      failures.map(({ source }) => source),
      ["Hugging Face"],
    );
    assert.deepEqual(
      alerts.map(({ source }) => source),
      ["OpenRouter"],
    );
    assert.deepEqual(await store.load(), {
      "huggingface:Qwen": ["Qwen/A"],
      "openrouter:qwen": ["qwen/qwen-x"],
    });
  });

  it("saves nothing when sending fails, so the next run sends again", async () => {
    const { hub, notifier, store, radar } = setup();
    hub.next = [qwen("A")];
    await radar().run();

    hub.next = [qwen("A", "B")];
    notifier.fail = true;
    await assert.rejects(radar().run(), /notifier down/);
    assert.deepEqual(await store.load(), { "huggingface:Qwen": ["Qwen/A"] });

    notifier.fail = false;
    assert.equal((await radar().run()).alerts.length, 1);
  });

  it("saves nothing on a dry run", async () => {
    const { hub, store, radar } = setup();
    hub.next = [qwen("A")];
    await radar(false).run();
    assert.deepEqual(await store.load(), {});
  });
});
