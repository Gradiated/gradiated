// A loopback stand-in for Anthropic and OpenAI. Tests script each reply and
// inspect exactly what reached the provider: path, headers and raw body bytes.
import {
  createServer,
  type IncomingHttpHeaders,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import type { Socket } from "node:net";

import {
  deferred,
  within,
  type Deferred,
} from "../../../../gateway/test/integration/eventually.js";

const GATE_TIMEOUT_MS = 10_000;

export interface Reply {
  readonly status?: number;
  readonly headers?: Record<string, string>;
  /** Sent as one body. Ignored when `chunks` is set. */
  readonly body?: string | Buffer;
  /** Sent as separate writes, in order, with chunked transfer encoding. */
  readonly chunks?: readonly (string | Buffer)[];
  /** Held before the response head is sent. */
  readonly beforeHeaders?: Deferred;
  /** Held after the first chunk, before the rest. */
  readonly afterFirstChunk?: Deferred;
  /** Keeps the response open after the chunks instead of ending it. */
  readonly stall?: boolean;
  /** After the chunks, writes `chunk` every `everyMs` until the peer leaves. */
  readonly drip?: { readonly chunk: string; readonly everyMs: number };
}

export interface ProviderRequest {
  readonly method: string;
  readonly path: string;
  readonly headers: IncomingHttpHeaders;
  readonly body: Buffer;
  /** Resolves when the response ends normally. */
  readonly finished: Deferred;
  /** Resolves when the peer closes the connection before the response ends. */
  readonly abandoned: Deferred;
}

export const JSON_REPLY =
  '{"id":"msg_1","type":"message","usage":{"input_tokens":3}}';

export class MockProvider {
  readonly requests: ProviderRequest[] = [];
  readonly errors: string[] = [];
  readonly url: string;

  readonly #server: Server;
  readonly #sockets = new Set<Socket>();
  readonly #replies: Reply[] = [];
  #arrival = deferred<ProviderRequest>();

  private constructor(server: Server) {
    this.#server = server;
    const address = server.address();
    if (address === null || typeof address === "string") {
      throw new Error("the mock provider has no TCP port");
    }

    this.url = `http://127.0.0.1:${address.port}`;
  }

  static async start(): Promise<MockProvider> {
    // Tests control disconnects explicitly; idle eviction must not race pooled requests.
    const server = createServer({ keepAliveTimeout: 0 });
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );

    const provider = new MockProvider(server);
    server.on("connection", (socket) => {
      provider.#sockets.add(socket);
      socket.on("close", () => provider.#sockets.delete(socket));
    });
    server.on("request", (request, response) => {
      void provider.#handle(request, response);
    });

    return provider;
  }

  reply(reply: Reply): void {
    this.#replies.push(reply);
  }

  /** The next request to arrive, or the one that already arrived first after the last call. */
  async next(timeoutMs = 5000): Promise<ProviderRequest> {
    const arrived = await within(this.#arrival.promise, timeoutMs);
    if (!arrived.settled) throw new Error("no request reached the provider");

    return arrived.value;
  }

  reset(): void {
    this.requests.length = 0;
    this.errors.length = 0;
    this.#replies.length = 0;
    this.#arrival = deferred();
  }

  async close(): Promise<void> {
    for (const socket of this.#sockets) socket.destroy();
    await new Promise<void>((resolve) => this.#server.close(() => resolve()));
  }

  async #handle(
    request: IncomingMessage,
    response: ServerResponse,
  ): Promise<void> {
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(Buffer.from(chunk));

    const recorded: ProviderRequest = {
      method: request.method ?? "",
      path: request.url ?? "",
      headers: request.headers,
      body: Buffer.concat(chunks),
      finished: deferred(),
      abandoned: deferred(),
    };
    response.on("finish", () => recorded.finished.resolve());
    response.on("close", () => {
      if (!response.writableFinished) recorded.abandoned.resolve();
    });

    this.requests.push(recorded);
    if (!this.#arrival.settled()) this.#arrival.resolve(recorded);

    const reply = this.#replies.shift() ?? {};
    try {
      await this.#respond(response, reply);
    } catch (error) {
      this.errors.push(error instanceof Error ? error.message : String(error));
      response.destroy();
    }
  }

  async #respond(response: ServerResponse, reply: Reply): Promise<void> {
    await held(reply.beforeHeaders, "beforeHeaders");

    const streaming = reply.chunks !== undefined;
    response.writeHead(reply.status ?? 200, {
      "content-type": streaming ? "text/event-stream" : "application/json",
      ...reply.headers,
    });

    if (!streaming) {
      response.end(reply.body ?? JSON_REPLY);
      return;
    }

    const [first, ...rest] = reply.chunks ?? [];
    if (first !== undefined) response.write(first);
    // Node buffers the head with the first write; flushing proves incremental delivery.
    response.flushHeaders();

    await held(reply.afterFirstChunk, "afterFirstChunk");
    for (const chunk of rest) response.write(chunk);

    if (reply.drip) {
      const { chunk, everyMs } = reply.drip;
      const timer = setInterval(() => response.write(chunk), everyMs);
      response.on("close", () => clearInterval(timer));
      return;
    }

    if (!reply.stall) response.end();
  }
}

const held = async (
  gate: Deferred | undefined,
  name: string,
): Promise<void> => {
  if (!gate) return;

  if (!(await within(gate.promise, GATE_TIMEOUT_MS)).settled) {
    throw new Error(`test did not release the ${name} gate`);
  }
};
