import { randomUUID } from "node:crypto";

import type { OrganizationRole } from "@gradiated/control";
import { jwt } from "better-auth/plugins";

export const TRAINING_TOKEN_AUDIENCE = "training";
export const TRAINING_TOKEN_LIFETIME_SECONDS = 10 * 60;

// The plugin's session token endpoint signs a token without a workspace.
export const DISABLED_JWT_PATHS = ["/token"];

export interface TrainingTokenSubject {
  userId: string;
  organizationId: string;
  workspaceId: string;
  role: OrganizationRole;
}

export interface TrainingToken {
  token: string;
  expiresAt: Date;
}

export type SignJwt = (input: {
  body: { payload: Record<string, unknown> };
}) => Promise<{ token: string }>;

export const trainingJwt = (issuer: string) =>
  jwt({
    jwks: {
      keyPairConfig: { alg: "ES256" },
      rotationInterval: 90 * 24 * 60 * 60,
    },
    jwt: {
      issuer,
      audience: TRAINING_TOKEN_AUDIENCE,
      expirationTime: `${TRAINING_TOKEN_LIFETIME_SECONDS}s`,
    },
    disableSettingJwtHeader: true,
  });

export const signTrainingToken = async (
  sign: SignJwt,
  subject: TrainingTokenSubject,
  now = new Date(),
): Promise<TrainingToken> => {
  const iat = Math.floor(now.getTime() / 1000);
  const exp = iat + TRAINING_TOKEN_LIFETIME_SECONDS;

  const { token } = await sign({
    body: {
      payload: {
        sub: `user:${subject.userId}`,
        org: subject.organizationId,
        ws: subject.workspaceId,
        role: subject.role,
        jti: randomUUID(),
        iat,
        exp,
      },
    },
  });

  return { token, expiresAt: new Date(exp * 1000) };
};
