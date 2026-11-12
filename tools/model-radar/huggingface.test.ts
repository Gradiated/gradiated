import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { HuggingFaceSource } from "./huggingface.ts";
import { fakeFetch, json } from "./testing.ts";

const API = HuggingFaceSource.API;

describe("HuggingFaceSource", () => {
  it("lists every repo of each org, following the next-page links", async () => {
    const page2 = `${API}?author=Qwen&limit=1000&cursor=abc`;
    const { send, calls } = fakeFetch({
      [`${API}?author=Qwen&limit=1000`]: json(
        [{ id: "Qwen/Qwen3.8-27B", pipeline_tag: "text-generation" }],
        { link: `<${page2}>; rel="next"` },
      ),
      [page2]: json([{ id: "Qwen/Qwen-Image-2.1" }]),
      [`${API}?author=reflection&limit=1000`]: json([]),
    });

    const scans = await new HuggingFaceSource(send, [
      "Qwen",
      "reflection",
    ]).scan();

    assert.deepEqual(scans, [
      {
        scope: "huggingface:Qwen",
        owner: "Qwen",
        models: [
          {
            id: "Qwen/Qwen3.8-27B",
            owner: "Qwen",
            name: "Qwen/Qwen3.8-27B",
            url: "https://huggingface.co/Qwen/Qwen3.8-27B",
            details: ["weights live"],
          },
          {
            id: "Qwen/Qwen-Image-2.1",
            owner: "Qwen",
            name: "Qwen/Qwen-Image-2.1",
            url: "https://huggingface.co/Qwen/Qwen-Image-2.1",
            details: ["weights live"],
          },
        ],
      },
      { scope: "huggingface:reflection", owner: "reflection", models: [] },
    ]);
    assert.equal(calls.length, 3);
  });

  it("does not follow a next-page link to another site", async () => {
    const { send, calls } = fakeFetch({
      [`${API}?author=Qwen&limit=1000`]: json([], {
        link: `<https://elsewhere.test/api/models?cursor=x>; rel="next"`,
      }),
    });
    await new HuggingFaceSource(send, ["Qwen"]).scan();
    assert.equal(calls.length, 1);
  });

  it("fails the scan when a listing fails", async () => {
    const { send } = fakeFetch({});
    await assert.rejects(
      new HuggingFaceSource(send, ["Qwen"]).scan(),
      /Hugging Face listing for Qwen failed \(HTTP 404\)/,
    );
  });
});
