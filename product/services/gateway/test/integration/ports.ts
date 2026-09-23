import { createServer } from "node:net";

export const freePort = (): Promise<number> =>
  new Promise((resolve, reject) => {
    const probe = createServer();
    probe.on("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      if (address === null || typeof address === "string") {
        probe.close(() => reject(new Error("the probe has no TCP port")));
        return;
      }

      probe.close(() => resolve(address.port));
    });
  });

export const portAvailable = (port: number): Promise<boolean> =>
  new Promise((resolve) => {
    const probe = createServer();
    probe.on("error", () => resolve(false));
    probe.listen(port, "127.0.0.1", () => probe.close(() => resolve(true)));
  });
