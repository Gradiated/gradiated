// Loopback-only, bounded HTTP fault server with out-of-band test controls.
//
// Scenario selection never uses customer request fields. Requests, assertions and
// events are accessible only to the owning test process, not via an admin endpoint.
import {
  createServer,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import type { AddressInfo } from "node:net";

import { profile as kevProfile } from "./kev.js";
import type { JsonObject, RuntimeProfile } from "./profile.js";
import { profile as vllmProfile } from "./vllm.js";

const BODY_LIMIT = 1024 * 1024;
const GATE_TIMEOUT_MS = 8000;
const PROFILES: Record<RuntimeKind, RuntimeProfile> = {
  kev: kevProfile,
  vllm: vllmProfile,
};

export type RuntimeKind = "kev" | "vllm";

export type Fault =
  | "ok"
  | "disconnect"
  | "invalid_json"
  | "oversize"
  | "missing_usage"
  | "missing_done"
  | "partial_disconnect"
  | "stall"
  | "wrong_content_type";

export interface Deferred<T = void> {
  readonly promise: Promise<T>;
  readonly resolve: (value: T) => void;
  readonly settled: () => boolean;
}

export const deferred = <T = void>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  let done = false;
  const promise = new Promise<T>((settle) => {
    resolve = (value) => {
      done = true;
      settle(value);
    };
  });
  return { promise, resolve, settled: () => done };
};

const waitFor = async (gate: Deferred, timeoutMs: number): Promise<boolean> => {
  let timer: NodeJS.Timeout | undefined;
  const expiry = new Promise<false>((resolve) => {
    timer = setTimeout(() => resolve(false), timeoutMs);
  });
  try {
    return await Promise.race([gate.promise.then(() => true), expiry]);
  } finally {
    clearTimeout(timer);
  }
};

export interface PlanOptions {
  fault?: Fault;
  status?: number;
  cached?: number;
  fragment?: number;
  gate?: Deferred;
  /** Rewrite the response body or the event list in place, to inject faults. */
  mutate?: (value: any) => void;
  errorUsage?: JsonObject;
}

export interface Plan {
  readonly fault: Fault;
  readonly status: number;
  readonly cached: number;
  readonly fragment: number;
  readonly gate: Deferred | undefined;
  readonly entered: Deferred;
  readonly mutate: ((value: any) => void) | undefined;
  readonly errorUsage: JsonObject | undefined;
}

/**
 * Where a runtime's successful responses come from. `synthetic` generates them from
 * the wire profile, which is deterministic and supports every fault. `proxy` forwards
 * to a real inference server, so the gateway sees real bytes; calls are still recorded
 * and faults still apply, but token counts are whatever the real model produced.
 */
export type Upstream =
  { kind: "synthetic" } | { kind: "proxy"; baseUrl: string };

export const SYNTHETIC: Upstream = { kind: "synthetic" };

export class Runtime {
  readonly calls: JsonObject[] = [];
  readonly errors: string[] = [];
  readonly url: string;

  readonly #profile: RuntimeProfile;
  readonly #model: string;
  readonly #token: string;
  readonly #upstream: Upstream;
  readonly #plans: Plan[] = [];
  readonly #server: Server;
  readonly #sockets = new Set<import("node:net").Socket>();
  readonly #stopping = deferred();

  private constructor(
    kind: RuntimeKind,
    model: string,
    token: string,
    upstream: Upstream,
    server: Server,
  ) {
    this.#profile = PROFILES[kind];
    this.#model = model;
    this.#token = token;
    this.#upstream = upstream;
    this.#server = server;
    const { port } = server.address() as AddressInfo;
    this.url = `http://127.0.0.1:${port}`;
  }

  static async start(
    kind: RuntimeKind,
    model: string,
    token: string,
    upstream: Upstream = SYNTHETIC,
  ): Promise<Runtime> {
    const server = createServer();
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    const runtime = new Runtime(kind, model, token, upstream, server);
    server.on("connection", (socket) => {
      runtime.#sockets.add(socket);
      socket.on("close", () => runtime.#sockets.delete(socket));
    });
    server.on("request", (request, response) => {
      void runtime.#handle(request, response);
    });
    return runtime;
  }

  enqueue(options: PlanOptions = {}): Plan {
    const plan: Plan = {
      fault: options.fault ?? "ok",
      status: options.status ?? 200,
      cached: options.cached ?? 0,
      fragment: options.fragment ?? 0,
      gate: options.gate,
      entered: deferred(),
      mutate: options.mutate,
      errorUsage: options.errorUsage,
    };
    this.#plans.push(plan);
    return plan;
  }

  async close(): Promise<void> {
    this.#stopping.resolve();
    for (const socket of this.#sockets) socket.destroy();
    await new Promise<void>((resolve) => this.#server.close(() => resolve()));
  }

  async #handle(
    request: IncomingMessage,
    response: ServerResponse,
  ): Promise<void> {
    if (request.method === "GET") {
      return reply(
        response,
        request.url === "/health" ? 200 : 404,
        Buffer.from("{}"),
      );
    }
    try {
      if (request.headers.authorization !== `Bearer ${this.#token}`) {
        return reply(
          response,
          401,
          Buffer.from('{"error":{"message":"unauthorized"}}'),
        );
      }
      if (request.url !== this.#profile.PATH)
        throw new Error(`unexpected path ${request.url}`);
      const body = JSON.parse(await readBody(request)) as JsonObject;
      this.#profile.validate(body, this.#model);
      this.calls.push(body);
      const plan = this.#plans.shift() ?? this.enqueueDefault();
      plan.entered.resolve();
      if (plan.gate && !(await waitFor(plan.gate, GATE_TIMEOUT_MS))) {
        if (!this.#stopping.settled())
          throw new Error("test did not release runtime gate");
        return;
      }
      if (plan.fault === "disconnect") return void request.socket.destroy();
      if (plan.status !== 200) {
        const error: JsonObject = {
          error: { message: "PRIVATE_RUNTIME_DETAIL" },
        };
        if (plan.errorUsage !== undefined) error.usage = plan.errorUsage;
        return reply(
          response,
          plan.status,
          Buffer.from(JSON.stringify(error)),
          plan.status === 307 ? { Location: "/must-not-follow" } : undefined,
        );
      }
      if (body.stream) return await this.#stream(response, body, plan);
      const result =
        this.#upstream.kind === "proxy"
          ? await this.#forward(body)
          : this.#profile.response(body, plan.cached);
      plan.mutate?.(result);
      if (plan.fault === "invalid_json") {
        return reply(
          response,
          200,
          Buffer.from("not json PRIVATE_RUNTIME_DETAIL"),
        );
      }
      if (plan.fault === "oversize") {
        // Declare a body far larger than the gateway's cap, then deliver nothing.
        response.writeHead(200, {
          "Content-Type": "application/json",
          "Content-Length": "8000001",
        });
        response.flushHeaders();
        return void response.socket?.destroy();
      }
      reply(response, 200, Buffer.from(JSON.stringify(result)));
    } catch (error) {
      if (isDisconnect(error)) return; // Deliberate cancellation and fault tests close sockets.
      this.errors.push(error instanceof Error ? error.message : String(error));
      try {
        reply(
          response,
          500,
          Buffer.from('{"error":{"message":"mock contract violation"}}'),
        );
      } catch {
        // The peer is already gone.
      }
    }
  }

  private enqueueDefault(): Plan {
    return {
      fault: "ok",
      status: 200,
      cached: 0,
      fragment: 0,
      gate: undefined,
      entered: deferred(),
      mutate: undefined,
      errorUsage: undefined,
    };
  }

  /** One non-streaming round trip to the real runtime, returned to the gateway as-is. */
  async #forward(body: JsonObject): Promise<JsonObject> {
    const upstream = this.#upstream as { baseUrl: string };
    const response = await fetch(`${upstream.baseUrl}${this.#profile.PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120_000),
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(
        `real runtime returned ${response.status}: ${text.slice(0, 400)}`,
      );
    }
    return JSON.parse(text) as JsonObject;
  }

  /** Relay the real runtime's SSE body byte for byte, so framing is the runtime's own. */
  async #relay(
    response: ServerResponse,
    body: JsonObject,
    plan: Plan,
  ): Promise<void> {
    const upstream = this.#upstream as { baseUrl: string };
    const source = await fetch(`${upstream.baseUrl}${this.#profile.PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120_000),
    });
    if (!source.ok || !source.body) {
      throw new Error(`real runtime returned ${source.status} for a stream`);
    }
    response.writeHead(200, {
      "Content-Type": source.headers.get("content-type") ?? "text/event-stream",
      Connection: "close",
    });
    try {
      for await (const chunk of source.body as unknown as AsyncIterable<Uint8Array>) {
        const payload = Buffer.from(chunk);
        const size = plan.fragment || payload.length;
        for (let offset = 0; offset < payload.length; offset += size) {
          await write(response, payload.subarray(offset, offset + size));
        }
      }
      response.end();
    } catch (error) {
      if (!isDisconnect(error)) this.errors.push(String(error));
      response.socket?.destroy();
    }
  }

  async #stream(
    response: ServerResponse,
    body: JsonObject,
    plan: Plan,
  ): Promise<void> {
    if (this.#upstream.kind === "proxy")
      return this.#relay(response, body, plan);
    let events = this.#profile.events(body, plan.cached);
    plan.mutate?.(events);
    if (plan.fault === "missing_usage") {
      events = events.filter(
        (event) => typeof event === "string" || !event.usage,
      );
    }
    if (plan.fault === "missing_done") events = events.slice(0, -1);
    response.writeHead(200, {
      "Content-Type":
        plan.fault === "wrong_content_type"
          ? "application/json"
          : "text/event-stream",
      Connection: "close",
    });
    void this.#writeEvents(response, events, plan);
  }

  // Node frames these writes as HTTP chunks, the same way a real SSE runtime does;
  // one write per `fragment` bytes is what puts frame boundaries at arbitrary offsets.
  async #writeEvents(
    response: ServerResponse,
    events: (JsonObject | string)[],
    plan: Plan,
  ): Promise<void> {
    try {
      for (const [index, event] of events.entries()) {
        if (plan.fault === "partial_disconnect" && index === 2) {
          return void response.socket?.destroy();
        }
        if (plan.fault === "stall" && index === 2) {
          await waitFor(this.#stopping, 5000);
          return void response.socket?.destroy();
        }
        const data = typeof event === "string" ? event : JSON.stringify(event);
        const payload = Buffer.from(`data: ${data}\r\n\r\n`);
        const size = plan.fragment || payload.length;
        for (let offset = 0; offset < payload.length; offset += size) {
          await write(response, payload.subarray(offset, offset + size));
        }
      }
      response.end();
    } catch (error) {
      if (!isDisconnect(error)) this.errors.push(String(error));
      response.socket?.destroy();
    }
  }
}

const isDisconnect = (error: unknown): boolean =>
  error instanceof Error &&
  [
    "EPIPE",
    "ECONNRESET",
    "ERR_STREAM_DESTROYED",
    "ERR_STREAM_WRITE_AFTER_END",
  ].includes((error as NodeJS.ErrnoException).code ?? "");

const write = (response: ServerResponse, chunk: Buffer): Promise<void> =>
  new Promise((resolve, reject) => {
    response.write(chunk, (error) => (error ? reject(error) : resolve()));
  });

const reply = (
  response: ServerResponse,
  status: number,
  body: Buffer,
  extra?: Record<string, string>,
): void => {
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": String(body.length),
    ...extra,
  });
  response.end(body);
};

const readBody = (request: IncomingMessage): Promise<string> =>
  new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    request.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > BODY_LIMIT) {
        reject(new Error("request body exceeded the bounded mock limit"));
        request.socket.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("error", reject);
    request.on("end", () => {
      if (size === 0) reject(new Error("empty request body"));
      else resolve(Buffer.concat(chunks).toString());
    });
  });
