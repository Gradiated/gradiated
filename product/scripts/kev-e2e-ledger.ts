/**
 * Observes real HTTP responses without modifying the SDK harness.
 *
 * Installed as a vitest setup file. It is inert unless the E2E launcher sets
 * KEV_E2E_RESPONSE_LEDGER, so the harness runs unchanged on its own. Only
 * `x-generation-id` from successful SystemOne responses at the local gateway origin
 * is recorded; no request bodies and no API keys are written.
 */
import { appendFileSync } from "node:fs";

const ledger = process.env.KEV_E2E_RESPONSE_LEDGER;
const origin = process.env.KEV_GATEWAY_BASE_URL;

if (ledger && origin) {
  const target = new URL(origin);
  const inner = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const response = await inner(input, init);
    try {
      const url = new URL(
        typeof input === "string" ? input : (input as Request).url,
      );
      const method = init?.method ?? (input as Request).method ?? "GET";
      const matches =
        url.protocol === target.protocol &&
        url.host === target.host &&
        url.pathname.replace(/\/$/, "").endsWith("/systemone") &&
        method.toUpperCase() === "POST" &&
        response.status === 200;
      if (matches) {
        const generationId = response.headers.get("x-generation-id");
        if (!generationId)
          throw new Error("Successful response lacks x-generation-id");
        if (!/^[0-9a-f-]{36}$/i.test(generationId)) {
          throw new Error(
            "Successful response has a malformed x-generation-id",
          );
        }
        appendFileSync(
          ledger,
          `${JSON.stringify({ generation_id: generationId })}\n`,
        );
      }
    } catch (error) {
      if (error instanceof TypeError) return response; // Not an absolute URL; ignore.
      throw error;
    }
    return response;
  };
}
