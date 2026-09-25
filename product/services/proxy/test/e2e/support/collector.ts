import { createServer, type IncomingHttpHeaders, type Server } from "node:http";

import type { JsonObject } from "../../../../gateway/test/integration/json.js";

export interface CollectorPost {
  readonly headers: IncomingHttpHeaders;
  readonly lines: readonly JsonObject[];
}

export const COLLECTOR_TOKEN = "collector-token-for-proxy-e2e";

/** A loopback stand-in for the collector that keeps every NDJSON batch it accepts. */
export class MockCollector {
  readonly posts: CollectorPost[] = [];
  readonly url: string;
  hang = false;

  readonly #server: Server;

  private constructor(server: Server, url: string) {
    this.#server = server;
    this.url = url;
  }

  static async start(): Promise<MockCollector> {
    const server = createServer();
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );

    const address = server.address();
    if (address === null || typeof address === "string") {
      throw new Error("the mock collector has no TCP port");
    }

    const collector = new MockCollector(
      server,
      `http://127.0.0.1:${address.port}/v1/contents`,
    );
    server.on("request", async (request, response) => {
      const chunks: Buffer[] = [];
      for await (const chunk of request) chunks.push(Buffer.from(chunk));

      const lines = Buffer.concat(chunks)
        .toString()
        .split("\n")
        .filter((line) => line !== "")
        .map((line) => JSON.parse(line) as JsonObject);
      collector.posts.push({ headers: request.headers, lines });

      if (!collector.hang) response.writeHead(202).end();
    });

    return collector;
  }

  get lines(): JsonObject[] {
    return this.posts.flatMap((post) => post.lines);
  }

  env(): Record<string, string> {
    return {
      PROXY_COLLECTOR_URL: this.url,
      PROXY_COLLECTOR_TOKEN: COLLECTOR_TOKEN,
    };
  }

  async close(): Promise<void> {
    this.#server.closeAllConnections();
    await new Promise<void>((resolve) => this.#server.close(() => resolve()));
  }
}
