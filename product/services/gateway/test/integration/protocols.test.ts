import { describe, expect, it } from "vitest";

import { useCases } from "./support.js";

const { makeCase } = useCases();

describe.each(["messages", "responses"])("%s protocol", (protocol) => {
  it.each([false, true])(
    "translates through the real runtime transport (stream=%s)",
    async (stream) => {
      const instance = await makeCase("vllm");
      const body =
        protocol === "messages"
          ? {
              model: instance.model,
              stream,
              messages: [{ role: "user", content: "Synthetic ticket" }],
              max_tokens: 16,
            }
          : {
              model: instance.model,
              stream,
              input: "Synthetic ticket",
              store: false,
            };
      const response = await instance.http.post(`/v1/${protocol}`, {
        headers: instance.headers,
        json: body,
      });
      expect(response.status, response.text).toBe(200);
      expect(instance.runtimes[0]!.calls).toHaveLength(1);
      expect(instance.runtimes[0]!.calls[0]!.messages).toBeTruthy();
      if (stream) {
        const terminal =
          protocol === "messages"
            ? "event: message_stop"
            : "event: response.completed";
        expect(response.text).toContain(terminal);
      } else {
        expect(response.json().model).toBe(instance.model);
        expect(
          response.json()[protocol === "messages" ? "content" : "output"],
        ).toBeTruthy();
      }
      await instance.settled(response, "succeeded", 1060);
    },
  );
});

describe.each(["messages", "responses", "chat/completions", "systemone"])(
  "%s rejects malformed bodies",
  (protocol) => {
    it("rejects broken and duplicate JSON", async () => {
      const instance = await makeCase(
        protocol === "systemone" ? "kev" : "vllm",
      );
      for (const body of ["{broken", '{"model":"first","model":"second"}']) {
        const response = await instance.http.post(`/v1/${protocol}`, {
          headers: { ...instance.headers, "Content-Type": "application/json" },
          content: body,
        });
        expect(response.status).toBe(400);
        expect(response.json().error.code).toBe("invalid_request");
      }
      expect(instance.runtimes[0]!.calls).toEqual([]);
      expect(await instance.settlements()).toEqual([]);
    });
  },
);

describe("stateful responses", () => {
  it.each([{ store: true }, { previous_response_id: "private/id" }])(
    "never reach the runtime (%o)",
    async (changes) => {
      const instance = await makeCase("vllm");
      const response = await instance.http.post("/v1/responses", {
        headers: instance.headers,
        json: { model: instance.model, input: "Synthetic", ...changes },
      });
      expect(response.status).toBe(400);
      expect(instance.runtimes[0]!.calls).toEqual([]);
      expect(await instance.settlements()).toEqual([]);
    },
  );
});
