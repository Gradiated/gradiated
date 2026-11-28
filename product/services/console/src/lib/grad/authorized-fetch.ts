export type TokenSource = (renew: boolean) => Promise<string>;

const requestUrl = (input: RequestInfo | URL) =>
  new URL(input instanceof Request ? input.url : String(input));

// The SDK retries thrown fetch errors as network failures; a refused token is
// an authentication failure, so it becomes a 401 problem response instead.
const tokenUnavailable = (error: unknown) =>
  Response.json(
    {
      status: 401,
      code: "training_token_unavailable",
      detail:
        error instanceof Error && error.message
          ? error.message
          : "Could not sign in to training.",
    },
    { status: 401, headers: { "Content-Type": "application/problem+json" } },
  );

// Adds the training JWT to requests for grad's API only, so presigned storage
// URLs never receive it. A 401 renews the token once and resends the request.
export const authorizedFetch =
  ({
    apiOrigin,
    token,
    fetch: send = (input, init) => globalThis.fetch(input, init),
  }: {
    apiOrigin: string;
    token: TokenSource;
    fetch?: typeof globalThis.fetch;
  }): typeof globalThis.fetch =>
  async (input, init) => {
    if (requestUrl(input).origin !== apiOrigin) return send(input, init);

    const attempt = async (renew: boolean) => {
      const headers = new Headers(
        init?.headers ?? (input instanceof Request ? input.headers : undefined),
      );

      try {
        headers.set("Authorization", `Bearer ${await token(renew)}`);
      } catch (error) {
        return tokenUnavailable(error);
      }

      return send(input, { ...init, headers });
    };

    const response = await attempt(false);
    if (response.status !== 401) return response;

    await response.body?.cancel();

    return attempt(true);
  };
