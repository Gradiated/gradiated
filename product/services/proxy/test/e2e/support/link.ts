// A TCP link between the proxy and one dependency that a test can break, so
// outages are real connection failures rather than configuration tricks.
import { connect, createServer, type Server, type Socket } from "node:net";

export type LinkState = "up" | "refusing" | "silent";

export class Link {
  readonly port: number;
  #state: LinkState = "up";

  readonly #server: Server;
  readonly #sockets = new Set<Socket>();

  private constructor(server: Server, port: number) {
    this.#server = server;
    this.port = port;
  }

  static async to(target: string): Promise<Link> {
    const { hostname, port } = new URL(target);
    const server = createServer();
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );

    const address = server.address();
    if (address === null || typeof address === "string") {
      throw new Error("the link has no TCP port");
    }

    const link = new Link(server, address.port);
    server.on("connection", (inbound) =>
      link.#accept(inbound, hostname, Number(port)),
    );

    return link;
  }

  /** The target URL with its host and port replaced by this link. */
  rewrite(target: string): string {
    const url = new URL(target);
    url.hostname = "127.0.0.1";
    url.port = String(this.port);

    return url.toString().replace(/\/$/, "");
  }

  /**
   * `refusing` resets existing and new connections; `silent` accepts new
   * connections and never answers, like a hung peer.
   */
  set(state: LinkState): void {
    this.#state = state;
    if (state === "up") return;

    for (const socket of this.#sockets) socket.destroy();
    this.#sockets.clear();
  }

  async close(): Promise<void> {
    this.set("refusing");
    await new Promise<void>((resolve) => this.#server.close(() => resolve()));
  }

  #accept(inbound: Socket, host: string, port: number): void {
    this.#sockets.add(inbound);
    inbound.on("close", () => this.#sockets.delete(inbound));
    inbound.on("error", () => inbound.destroy());

    if (this.#state === "refusing") {
      inbound.resetAndDestroy();
      return;
    }

    if (this.#state === "silent") return;

    const outbound = connect(port, host);
    this.#sockets.add(outbound);
    outbound.on("close", () => {
      this.#sockets.delete(outbound);
      inbound.destroy();
    });
    outbound.on("error", () => inbound.destroy());
    inbound.on("close", () => outbound.destroy());
    inbound.pipe(outbound).pipe(inbound);
  }
}
