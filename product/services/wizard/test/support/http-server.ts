import { createServer, type RequestListener } from "node:http";
import { test as base } from "vitest";

export interface RunningServer {
  baseUrl: string;
  close: () => Promise<void>;
}

export type Serve = (handler: RequestListener) => Promise<RunningServer>;

export const startServer: Serve = async (handler) => {
  const server = createServer(handler);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

  const address = server.address();
  if (address === null || typeof address === "string") {
    throw new Error("The test server is not listening on a TCP port.");
  }

  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    close: () =>
      new Promise((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      ),
  };
};

export const unreachableUrl = async (): Promise<string> => {
  const server = await startServer(() => undefined);
  await server.close();

  return server.baseUrl;
};

export const test = base.extend("serve", async ({}, { onCleanup }) => {
  const servers: RunningServer[] = [];
  onCleanup(async () => {
    await Promise.all(servers.map((server) => server.close()));
  });

  const serve: Serve = async (handler) => {
    const server = await startServer(handler);
    servers.push(server);

    return server;
  };

  return serve;
});
