import { randomUUID } from "node:crypto";

// Better Auth's jwt() plugin signer; it adds the issuer and the `training` audience.
export type SignJwt = (input: {
  body: { payload: Record<string, unknown> };
}) => Promise<{ token: string }>;

export const SERVICE_TOKEN_LIFETIME_SECONDS = 5 * 60;

/** Service JWTs for the product's calls to grad: one workspace, named scopes. */
export const createServiceTokens =
  (sign: SignJwt, service = "inference") =>
  async (call: {
    workspaceId: string;
    scopes: readonly string[];
  }): Promise<string> => {
    const iat = Math.floor(Date.now() / 1000);
    const { token } = await sign({
      body: {
        payload: {
          sub: `service:${service}`,
          ws: call.workspaceId,
          scopes: [...call.scopes],
          jti: randomUUID(),
          iat,
          exp: iat + SERVICE_TOKEN_LIFETIME_SECONDS,
        },
      },
    });

    return token;
  };
