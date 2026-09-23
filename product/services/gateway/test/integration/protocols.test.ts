import { describe, expect, it } from "vitest";

import { expectRejected, type Rejection } from "./assertions.js";
import { useCases, type Case, type SettlementStatus } from "./case.js";
import type { JsonObject } from "./json.js";
import type { Fault } from "./mock-runtimes/server.js";

const { makeCase } = useCases();

type Protocol = "messages" | "responses";

const TERMINAL_EVENT: Record<Protocol, string> = {
  messages: "event: message_stop",
  responses: "event: response.completed",
};

const protocolBody = (
  protocol: Protocol,
  instance: Case,
  stream: boolean,
): JsonObject =>
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

describe.each<Protocol>(["messages", "responses"])(
  "%s protocol",
  (protocol) => {
    const send = (instance: Case, stream: boolean) =>
      instance.http.post(`/v1/${protocol}`, {
        headers: instance.headers,
        json: protocolBody(protocol, instance, stream),
      });

    it.each([false, true])(
      "translates through the real runtime transport (stream=%s)",
      async (stream) => {
        const instance = await makeCase("vllm");

        const response = await send(instance, stream);

        expect(response.status, response.text).toBe(200);
        expect(instance.runtimes[0]!.calls).toHaveLength(1);
        expect(instance.runtimes[0]!.calls[0]!.messages).toBeTruthy();
        if (stream) {
          expect(response.text).toContain(TERMINAL_EVENT[protocol]);
        } else {
          expect(response.json().model).toBe(instance.model);
          expect(
            response.json()[protocol === "messages" ? "content" : "output"],
          ).toBeTruthy();
        }
        await instance.settled(response, { charge: 1060 });
      },
    );

    it.each<{ status: number; rejection: Rejection }>([
      { status: 500, rejection: { code: "runtime_unavailable" } },
      { status: 503, rejection: { code: "capacity_exceeded" } },
    ])(
      "sanitizes and settles a runtime $status in its own envelope",
      async ({ status, rejection }) => {
        const instance = await makeCase("vllm");
        instance.runtimes[0]!.enqueue({ status });

        const response = await send(instance, false);

        expectRejected(response, rejection);
        if (protocol === "messages") expect(response.json().type).toBe("error");
        expect(response.text).not.toContain("PRIVATE_RUNTIME_DETAIL");
        await instance.settled(response, { status: "failed", charge: 0 });
      },
    );

    it.each<{ fault: Fault; settles: SettlementStatus }>([
      { fault: "partial_disconnect", settles: "failed" },
      { fault: "missing_usage", settles: "failed" },
      { fault: "stall", settles: "cancelled" },
    ])(
      "ends an incomplete stream ($fault) with an error event",
      async ({ fault, settles }) => {
        const instance = await makeCase("vllm");
        instance.runtimes[0]!.enqueue({ fault });

        const response = await send(instance, true);

        expect(response.status).toBe(200);
        expect(response.text).not.toContain(TERMINAL_EVENT[protocol]);
        expect(response.text).toContain("event: error");
        expect(response.text).not.toContain("PRIVATE_RUNTIME_DETAIL");
        await instance.settled(response, { status: settles });
      },
    );
  },
);

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
        expectRejected(response, { code: "invalid_request" });
      }
      await instance.expectNotDispatched();
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

      expectRejected(response, { code: "invalid_request" });
      await instance.expectNotDispatched();
    },
  );
});
