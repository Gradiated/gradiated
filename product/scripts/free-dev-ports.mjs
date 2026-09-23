import { stopListeners } from "./dev-ports.mjs";

const ports = process.argv.slice(2).map(Number);

if (
  ports.length === 0 ||
  ports.some((port) => !Number.isInteger(port) || port < 1 || port > 65_535)
) {
  throw new Error("Pass one or more valid TCP ports.");
}

await stopListeners(ports);
