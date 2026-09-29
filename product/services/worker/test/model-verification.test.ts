import { randomUUID } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  ModelVerificationInputSchema,
  verifyModel,
} from "../src/model-verification.js";

const options = () => ({
  apiKey: "synthetic-test-key",
  baseURL: "https://gateway.test",
  modelId: "test/model",
  signal: AbortSignal.timeout(5000),
});
const response = (body: unknown, generation = randomUUID()) =>
  Response.json(body, { headers: { "x-gradiated-generation-id": generation } });
const decision = {
  model: "test/model",
  usage: { input_tokens: 20, output_tokens: 0 },
  answers: { category: { type: "choice", choice: "billing" } },
};

describe("production SDK verification", () => {
  const rollout = {
    modelId: "test/model",
    stage: "canary",
    runtimeRevision: "test-release",
  };

  it("accepts Nomad allocation IDs without RFC UUID version or variant bits", () => {
    for (const id of [
      "4a7fca4c-20c8-1ac4-6535-051217442d22",
      "eeb45cf5-037b-b48c-0a90-855453cf3572",
    ]) {
      expect(
        ModelVerificationInputSchema.parse({ ...rollout, deploymentIds: [id] })
          .deploymentIds,
      ).toEqual([id]);
    }
  });

  it.each([
    "",
    "not-an-id",
    "../../another-allocation",
    "eeb45cf5-037b-b48c-0a90-855453cf357Z",
  ])("rejects malformed allocation ID %s", (id) => {
    expect(() =>
      ModelVerificationInputSchema.parse({ ...rollout, deploymentIds: [id] }),
    ).toThrow();
  });

  it("uses the actual TypeSafe SDK and targets the requested allocation", async () => {
    const id = randomUUID();
    const result = await verifyModel({
      ...options(),
      protocol: "system_one",
      deploymentId: id,
      fetch: async (input) => {
        const request = input as Request;
        expect(request.url).toBe("https://gateway.test/v1/systemone");
        expect(request.headers.get("x-gradiated-verification-deployment")).toBe(
          id,
        );
        expect((await request.json()).model).toBe("test/model");
        const result = response(decision);
        result.headers.set("x-gradiated-verification-deployment", id);
        return result;
      },
    });
    expect(result.generations).toHaveLength(1);
  });

  it.each([undefined, "00000000-0000-4000-8000-000000000001"])(
    "rejects an unacknowledged target (%s)",
    async (acknowledged) => {
      await expect(
        verifyModel({
          ...options(),
          protocol: "system_one",
          deploymentId: randomUUID(),
          fetch: async () => {
            const result = response(decision);
            if (acknowledged)
              result.headers.set(
                "x-gradiated-verification-deployment",
                acknowledged,
              );
            return result;
          },
        }),
      ).rejects.toThrow();
    },
  );

  it.each(["wrong-answer", "missing-generation", "wrong-usage", "http-error"])(
    "rejects %s",
    async (failure) => {
      await expect(
        verifyModel({
          ...options(),
          protocol: "system_one",
          fetch: async () => {
            if (failure === "http-error")
              return new Response("unavailable", { status: 503 });
            if (failure === "missing-generation")
              return Response.json(decision);
            return response({
              ...decision,
              ...(failure === "wrong-answer"
                ? {
                    answers: {
                      category: { type: "choice", choice: "technical" },
                    },
                  }
                : { usage: { input_tokens: 20, output_tokens: 1 } }),
            });
          },
        }),
      ).rejects.toThrow();
    },
  );

  it.each([true, false])(
    "requires a completed OpenAI stream with usage (%s)",
    async (complete) => {
      let calls = 0;
      const result = verifyModel({
        ...options(),
        fetch: async (input) => {
          const request = input as Request;
          expect(
            request.headers.has("x-gradiated-verification-deployment"),
          ).toBe(false);
          const body = await request.json();
          calls++;
          if (!body.stream)
            return response({
              id: "completion",
              model: "test/model",
              choices: [
                { finish_reason: "stop", message: { content: "READY" } },
              ],
              usage: { completion_tokens: 1 },
            });
          const chunks = [
            {
              choices: [
                {
                  delta: { content: "READY" },
                  finish_reason: complete ? "stop" : null,
                },
              ],
            },
            ...(complete
              ? [{ choices: [], usage: { completion_tokens: 1 } }]
              : []),
          ];
          return new Response(
            chunks
              .map(
                (chunk) =>
                  `data: ${JSON.stringify({ id: "stream", model: "test/model", ...chunk })}\n\n`,
              )
              .join("") + "data: [DONE]\n\n",
            {
              headers: {
                "content-type": "text/event-stream",
                "x-gradiated-generation-id": randomUUID(),
              },
            },
          );
        },
      });
      if (complete) expect((await result).generations).toHaveLength(2);
      else
        await expect(result).rejects.toThrow("Incomplete streamed completion");
      expect(calls).toBe(2);
    },
  );
});
