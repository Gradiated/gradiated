import { lookup as dnsLookup, type LookupAddress } from "node:dns";
import { BlockList, isIP } from "node:net";

import { Agent, fetch as undiciFetch } from "undici";

const MAX_RESPONSE_BYTES = 4 * 1024 * 1024;

export class OutboundError extends Error {}

// Separate lists: an IPv6 rule for mapped addresses would also match every IPv4 address.
const blockedV4 = new BlockList();
const blockedV6 = new BlockList();
for (const [network, prefix] of [
  ["0.0.0.0", 8],
  ["10.0.0.0", 8],
  ["100.64.0.0", 10],
  ["127.0.0.0", 8],
  ["169.254.0.0", 16],
  ["172.16.0.0", 12],
  ["192.0.0.0", 24],
  ["192.0.2.0", 24],
  ["192.168.0.0", 16],
  ["198.18.0.0", 15],
  ["198.51.100.0", 24],
  ["203.0.113.0", 24],
  ["224.0.0.0", 3],
] as const)
  blockedV4.addSubnet(network, prefix, "ipv4");
for (const [network, prefix] of [
  ["::", 127],
  ["::ffff:0:0", 96],
  ["64:ff9b::", 96],
  ["100::", 64],
  ["2001:db8::", 32],
  ["fc00::", 7],
  ["fe80::", 10],
  ["ff00::", 8],
] as const)
  blockedV6.addSubnet(network, prefix, "ipv6");

export const isPublicAddress = (address: string): boolean => {
  const family = isIP(address);
  if (family === 0) return false;

  const mapped = address.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/i)?.[1];
  if (mapped) return isPublicAddress(mapped);

  return family === 4
    ? !blockedV4.check(address, "ipv4")
    : !blockedV6.check(address, "ipv6");
};

// Checking the addresses the connection actually uses also covers DNS rebinding and redirects.
const publicLookup: typeof dnsLookup = ((
  hostname: string,
  options: object,
  callback: (
    error: NodeJS.ErrnoException | null,
    address: string | LookupAddress[],
    family?: number,
  ) => void,
) =>
  dnsLookup(hostname, { ...options, all: true }, (error, addresses) => {
    if (error) return callback(error, []);

    const allowed = addresses.filter(({ address }) => isPublicAddress(address));
    if (!allowed.length)
      return callback(
        new OutboundError(`${hostname} does not resolve to a public address.`),
        [],
      );

    if ((options as { all?: boolean }).all) return callback(null, allowed);

    callback(null, allowed[0]!.address, allowed[0]!.family);
  })) as typeof dnsLookup;

const limitBody = (body: ReadableStream<Uint8Array>) => {
  let received = 0;

  return body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform: (chunk, controller) => {
        received += chunk.byteLength;
        if (received > MAX_RESPONSE_BYTES)
          controller.error(
            new OutboundError("The MCP server's response is too large."),
          );
        else controller.enqueue(chunk);
      },
    }),
  );
};

export interface OutboundOptions {
  allowPrivateNetworks: boolean;
}

// A fetch for user-supplied URLs: public addresses only, no redirects, bounded responses.
export const createOutboundFetch = ({
  allowPrivateNetworks,
}: OutboundOptions): typeof fetch => {
  const dispatcher = new Agent({
    connect: allowPrivateNetworks ? {} : { lookup: publicLookup },
    headersTimeout: 30_000,
    bodyTimeout: 60_000,
  });

  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(input instanceof Request ? input.url : input);
    if (!allowPrivateNetworks) {
      if (url.protocol !== "https:")
        throw new OutboundError("MCP servers must use HTTPS.");
      const literal = url.hostname.replace(/^\[|\]$/g, "");
      if (isIP(literal) && !isPublicAddress(literal))
        throw new OutboundError(`${url.hostname} is not a public address.`);
    }

    const response = await undiciFetch(url, {
      ...(init as object),
      redirect: "manual",
      dispatcher,
    }).catch((error: unknown) => {
      // undici reports a refused lookup as "fetch failed" with the reason as its cause.
      if (error instanceof Error && error.cause instanceof OutboundError)
        throw error.cause;
      throw error;
    });
    if (response.status >= 300 && response.status < 400)
      throw new OutboundError("The MCP server redirected the request.");

    return new Response(
      response.body
        ? limitBody(response.body as ReadableStream<Uint8Array>)
        : null,
      {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers as unknown as Headers,
      },
    );
  }) as typeof fetch;
};
