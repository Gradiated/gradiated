// Minimal HTTP client with the raw control these tests need: repeated headers,
// oversized bodies, and streams the caller can abandon mid-frame.
import {
  request as httpRequest,
  type IncomingMessage,
  type OutgoingHttpHeaders,
} from "node:http";

import { isJsonObject, object, type JsonObject } from "./json.js";

export type Headers = OutgoingHttpHeaders;

type Method = "GET" | "POST" | "OPTIONS";

export interface Options {
  headers?: Headers;
  json?: unknown;
  content?: string | Buffer;
  timeoutMs?: number;
}

export class Response {
  constructor(
    readonly status: number,
    readonly headers: Record<string, string>,
    readonly text: string,
  ) {}

  json(): JsonObject {
    const value: unknown = JSON.parse(this.text);
    if (!isJsonObject(value)) {
      throw new Error(`expected a JSON object body: ${this.text}`);
    }

    return value;
  }

  /** Both the OpenAI body and the Anthropic `{type: "error"}` envelope carry `error`. */
  error(): PublicError {
    const { type, code, message, param = null } = object(this.json().error);

    if (
      typeof type !== "string" ||
      typeof code !== "string" ||
      typeof message !== "string" ||
      (param !== null && typeof param !== "string")
    ) {
      throw new Error(`expected a public error body: ${this.text}`);
    }

    return { type, code, message, param };
  }
}

export interface PublicError {
  readonly type: string;
  readonly code: string;
  readonly message: string;
  readonly param: string | null;
}

export class StreamResponse {
  constructor(
    readonly status: number,
    readonly headers: Record<string, string>,
    readonly message: IncomingMessage,
  ) {}

  async *lines(): AsyncGenerator<string> {
    // Decode across chunks, so a read boundary inside a multibyte character
    // does not split it.
    this.message.setEncoding("utf8");
    let buffer = "";

    for await (const chunk of this.message) {
      buffer += String(chunk);

      let index: number;
      while ((index = buffer.search(/\r\n|\n/)) !== -1) {
        const line = buffer.slice(0, index);
        buffer = buffer.slice(
          index + (buffer.startsWith("\r\n", index) ? 2 : 1),
        );
        yield line;
      }
    }

    if (buffer.length > 0) yield buffer;
  }

  /** Frames of an SSE body, without the `data:` prefix. */
  async dataFrames(): Promise<string[]> {
    const frames: string[] = [];
    for await (const line of this.lines()) {
      if (line.startsWith("data:")) frames.push(line.slice(5).trim());
    }

    return frames;
  }
}

const normalize = (message: IncomingMessage): Record<string, string> =>
  Object.fromEntries(
    Object.entries(message.headers).map(([key, value]) => [
      key,
      Array.isArray(value) ? value.join(", ") : (value ?? ""),
    ]),
  );

export class Client {
  constructor(
    readonly baseUrl: string,
    private readonly defaultTimeoutMs = 8000,
  ) {}

  post(path: string, options: Options = {}): Promise<Response> {
    return this.request("POST", path, options);
  }

  get(path: string, options: Options = {}): Promise<Response> {
    return this.request("GET", path, options);
  }

  options(path: string, options: Options = {}): Promise<Response> {
    return this.request("OPTIONS", path, options);
  }

  private async request(
    method: Method,
    path: string,
    options: Options = {},
  ): Promise<Response> {
    const { message } = await this.send(method, path, options);
    const chunks: Buffer[] = [];
    for await (const chunk of message) chunks.push(Buffer.from(chunk));

    return new Response(
      message.statusCode ?? 0,
      normalize(message),
      Buffer.concat(chunks).toString(),
    );
  }

  async stream(path: string, options: Options = {}): Promise<StreamResponse> {
    const { message } = await this.send("POST", path, options);

    return new StreamResponse(
      message.statusCode ?? 0,
      normalize(message),
      message,
    );
  }

  private send(
    method: Method,
    path: string,
    options: Options,
  ): Promise<{ message: IncomingMessage }> {
    const url = new URL(path, this.baseUrl);
    const body =
      options.json !== undefined
        ? Buffer.from(JSON.stringify(options.json))
        : options.content !== undefined
          ? Buffer.from(options.content)
          : undefined;
    const timeoutMs = options.timeoutMs ?? this.defaultTimeoutMs;

    const headers: Headers = { ...options.headers };
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (body) headers["Content-Length"] = String(body.length);

    return new Promise((resolve, reject) => {
      const request = httpRequest(
        {
          protocol: url.protocol,
          hostname: url.hostname,
          port: url.port,
          path: url.pathname + url.search,
          method,
          headers,
          // Never inherit ambient proxy or agent configuration.
          agent: false,
        },
        (message) => resolve({ message }),
      );
      request.setTimeout(timeoutMs, () => {
        request.destroy(new Error(`timed out after ${timeoutMs}ms`));
      });
      request.on("error", reject);

      if (body) request.write(body);
      request.end();
    });
  }
}
